# Netlify/Vercel Serverless Function
# This handles Stripe webhook and generates Telegram invite link

import json
import os
import stripe
import asyncio
import threading
import aiohttp
import requests
from telegram import Bot
from datetime import datetime, timedelta

# Environment variables
stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_GROUP_ID = os.environ.get('TELEGRAM_GROUP_ID', '-1003798603747')
STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET')

# Telegram Bot API base URL
TELEGRAM_API_URL = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}'

# Initialize Telegram Bot for creating links
bot = Bot(token=TELEGRAM_BOT_TOKEN) if TELEGRAM_BOT_TOKEN else None

# Simple in-memory storage (use Redis or database in production)
invite_links = {}


def run_async(coro):
    """Run async code in serverless environment"""
    result = {'value': None, 'error': None}

    def run_in_thread():
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result['value'] = loop.run_until_complete(coro)
            loop.close()
        except Exception as e:
            result['error'] = e

    thread = threading.Thread(target=run_in_thread)
    thread.start()
    thread.join()

    if result['error']:
        raise result['error']
    return result['value']


async def create_telegram_invite_link():
    """Create one-time Telegram invite link"""
    expire_date = int((datetime.now() + timedelta(seconds=3600)).timestamp())
    invite_link = await bot.create_chat_invite_link(
        chat_id=TELEGRAM_GROUP_ID,
        expire_date=expire_date,
        member_limit=1
    )
    return invite_link.invite_link


async def unban_user(user_id):
    """Unban a user from the Telegram group using direct API call"""
    try:
        api_url = f'{TELEGRAM_API_URL}/unbanChatMember'

        payload = {
            'chat_id': int(TELEGRAM_GROUP_ID),
            'user_id': int(user_id),
            'only_if_banned': False
        }

        response = requests.post(api_url, json=payload, timeout=10)
        data = response.json()

        print(f"Telegram API Response: {data}")

        if data.get('ok'):
            return {'success': True, 'message': 'User unbanned successfully', 'details': data}
        error_description = data.get('description', 'Unknown error')
        print(f"Telegram API error: {error_description}")
        return {'success': False, 'message': f'Failed to unban: {error_description}', 'details': data}
    except Exception as e:
        error_msg = str(e)
        print(f"Exception in unban_user: {error_msg}")
        return {'success': False, 'message': f'Error: {error_msg}'}


def unban_user_sync(user_id):
    """Synchronous wrapper for unban operation"""
    try:
        api_url = f'{TELEGRAM_API_URL}/unbanChatMember'

        payload = {
            'chat_id': int(TELEGRAM_GROUP_ID),
            'user_id': int(user_id),
            'only_if_banned': False
        }

        print(f"Sending unban request for user {user_id} to chat {TELEGRAM_GROUP_ID}")
        response = requests.post(api_url, json=payload, timeout=10)
        data = response.json()

        print(f"Telegram API Response: {data}")

        if data.get('ok'):
            return {'success': True, 'message': 'User unbanned successfully'}
        error_description = data.get('description', 'Unknown error')
        print(f"Telegram API error: {error_description}")
        return {'success': False, 'message': f'Failed to unban: {error_description}'}
    except Exception as e:
        error_msg = str(e)
        print(f"Exception in unban_user_sync: {error_msg}")
        return {'success': False, 'message': f'Error: {error_msg}'}


def handler(event, context):
    """Serverless function handler"""

    # Handle CORS preflight
    if event.get('httpMethod') == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'POST, GET, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type, Stripe-Signature',
            },
            'body': ''
        }

    # Handle unban request
    if event.get('httpMethod') == 'POST':
        try:
            body = json.loads(event.get('body', '{}'))

            # Check if this is an unban request
            if body.get('action') == 'unban' or 'unban' in event.get('path', ''):
                user_id = body.get('user_id')

                if not user_id:
                    return {
                        'statusCode': 400,
                        'headers': {
                            'Access-Control-Allow-Origin': '*',
                            'Content-Type': 'application/json',
                        },
                        'body': json.dumps({'success': False, 'message': 'user_id is required'})
                    }

                # Call synchronous unban function
                result = unban_user_sync(int(user_id))

                return {
                    'statusCode': 200,
                    'headers': {
                        'Access-Control-Allow-Origin': '*',
                        'Content-Type': 'application/json',
                    },
                    'body': json.dumps(result)
                }
        except json.JSONDecodeError:
            pass
        except Exception as e:
            return {
                'statusCode': 500,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Content-Type': 'application/json',
                },
                'body': json.dumps({'success': False, 'message': str(e)})
            }

    # Handle GET request for invite link retrieval
    if event.get('httpMethod') == 'GET':
        path = event.get('path', '')
        payment_id = path.split('/')[-1]

        if payment_id in invite_links:
            return {
                'statusCode': 200,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Content-Type': 'application/json',
                },
                'body': json.dumps({
                    'invite_link': invite_links[payment_id],
                    'status': 'ready'
                })
            }
        return {
            'statusCode': 202,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Content-Type': 'application/json',
            },
            'body': json.dumps({'status': 'processing'})
        }

    # Handle Stripe webhook (only if it has Stripe signature)
    stripe_signature = event.get('headers', {}).get('stripe-signature', '')
    if stripe_signature and event.get('httpMethod') == 'POST':
        try:
            payload = event.get('body', '')

            # Verify webhook signature
            webhook_event = stripe.Webhook.construct_event(
                payload, stripe_signature, STRIPE_WEBHOOK_SECRET
            )

            # Handle checkout.session.completed event
            if webhook_event['type'] == 'checkout.session.completed':
                session = webhook_event['data']['object']
                payment_id = session['payment_intent']

                # Generate Telegram invite link
                invite_link = run_async(create_telegram_invite_link())

                # Store it
                invite_links[payment_id] = invite_link

                print(f"Generated invite link for payment {payment_id}")

            return {
                'statusCode': 200,
                'body': json.dumps({'received': True})
            }

        except Exception as e:
            print(f"Stripe Error: {str(e)}")
            return {
                'statusCode': 400,
                'body': json.dumps({'error': str(e)})
            }

    # Handle health check
    if event.get('httpMethod') == 'GET' and 'health' in event.get('path', ''):
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Content-Type': 'application/json',
            },
            'body': json.dumps({
                'status': 'healthy',
                'bot_token_present': bool(TELEGRAM_BOT_TOKEN),
                'group_id': TELEGRAM_GROUP_ID,
                'function': 'netlify_function'
            })
        }

    # Default response if no handler matched
    return {
        'statusCode': 400,
        'headers': {
            'Access-Control-Allow-Origin': '*',
            'Content-Type': 'application/json',
        },
        'body': json.dumps({'error': 'Invalid request'})
    }


# For Vercel

def main(request):
    return handler(request, None)
