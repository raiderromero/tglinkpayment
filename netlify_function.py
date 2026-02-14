# Netlify/Vercel Serverless Function
# This handles Stripe webhook and generates Telegram invite link

import json
import os
import stripe
import asyncio
import threading
from telegram import Bot
from datetime import datetime, timedelta

# Environment variables
stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_GROUP_ID = int(os.environ.get('TELEGRAM_GROUP_ID'))
STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET')

# Initialize Telegram Bot
bot = Bot(token=TELEGRAM_BOT_TOKEN)

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
        else:
            return {
                'statusCode': 202,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Content-Type': 'application/json',
                },
                'body': json.dumps({'status': 'processing'})
            }
    
    # Handle Stripe webhook
    try:
        payload = event.get('body', '')
        sig_header = event.get('headers', {}).get('stripe-signature', '')
        
        # Verify webhook signature
        webhook_event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
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
        print(f"Error: {str(e)}")
        return {
            'statusCode': 400,
            'body': json.dumps({'error': str(e)})
        }

# For Vercel
def main(request):
    return handler(request, None)
