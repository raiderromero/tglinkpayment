import stripe
import asyncio
from telegram import Bot
from telegram.error import TelegramError
import logging
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
import os
from dotenv import load_dotenv
import threading

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)

# Enable CORS for all routes - Update with your domain
CORS(app, resources={
    r"/*": {
        "origins": ["https://machoriviera.com", "http://machoriviera.com", "http://localhost:*"],
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type"]
    }
})

# API Keys from environment variables
# NOTE: Backend needs SECRET key (sk_live_...), not publishable key (pk_live_...)
# Get your secret key from: https://dashboard.stripe.com/account/apikeys
STRIPE_API_KEY = os.getenv('STRIPE_API_KEY', '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')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET', 'whsec_BjLrYyKWAtEevOjChzFoucdE9cIgi61s')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '8227364388:AAH429ofpnoUE-i3kMGUQDylRJKWtxMgFJ4')
TELEGRAM_GROUP_ID = int(os.getenv('TELEGRAM_GROUP_ID', '-1003798603747'))  # The specific group ID

# Initialize Stripe
stripe.api_key = STRIPE_API_KEY

# Initialize Telegram Bot
bot = Bot(token=TELEGRAM_BOT_TOKEN)

# Store invite links temporarily (in production, use Redis or database)
invite_links_storage = {}


def run_async(coro):
    """Helper function to run async code in Flask routes using a separate thread"""
    result = {'value': None, 'error': None}
    
    def run_in_thread():
        try:
            # Create a new event loop for this thread
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


class StripePaymentHandler:
    """Handles Stripe payment events and sends Telegram notifications"""

    @staticmethod
    async def create_telegram_invite_link(expire_seconds: int = 3600) -> str:
        """
        Create a one-time use invite link for the Telegram group.
        
        Args:
            expire_seconds: Link expiration time in seconds (default: 1 hour)
            
        Returns:
            str: The invite link URL
        """
        try:
            # Calculate expiration time as Unix timestamp
            expire_date = int((datetime.now() + timedelta(seconds=expire_seconds)).timestamp())
            
            # Create a new invite link with expiration
            invite_link = await bot.create_chat_invite_link(
                chat_id=TELEGRAM_GROUP_ID,
                expire_date=expire_date,
                member_limit=1  # Limit to 1 user for security
            )
            logger.info(f"Created invite link: {invite_link.invite_link}")
            return invite_link.invite_link
        except TelegramError as e:
            logger.error(f"Error creating Telegram invite link: {e}")
            raise

    @staticmethod
    def store_invite_link(payment_id: str, invite_link: str) -> None:
        """
        Store the invite link for a payment ID.
        
        Args:
            payment_id: The Stripe payment ID
            invite_link: The generated invite link
        """
        invite_links_storage[payment_id] = {
            'link': invite_link,
            'created_at': datetime.now()
        }
        logger.info(f"Stored invite link for payment {payment_id}")
    
    @staticmethod
    def get_invite_link(payment_id: str) -> str:
        """
        Retrieve the invite link for a payment ID.
        
        Args:
            payment_id: The Stripe payment ID
            
        Returns:
            str: The invite link or None if not found
        """
        link_data = invite_links_storage.get(payment_id)
        if link_data:
            return link_data['link']
        return None

    @staticmethod
    def verify_webhook_signature(payload: bytes, sig_header: str) -> bool:
        """
        Verify that the webhook came from Stripe.
        
        Args:
            payload: Raw request body
            sig_header: Stripe signature header
            
        Returns:
            bool: True if signature is valid
        """
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, STRIPE_WEBHOOK_SECRET
            )
            return True
        except ValueError:
            logger.error("Invalid payload")
            return False
        except stripe.error.SignatureVerificationError:
            logger.error("Invalid signature")
            return False

    @staticmethod
    async def handle_payment_success(event: dict) -> bool:
        """
        Handle successful payment event from Stripe.
        
        Args:
            event: Stripe event dictionary
            
        Returns:
            bool: True if handling was successful
        """
        try:
            # Extract payment intent details
            payment_intent = event['data']['object']
            payment_id = payment_intent['id']
            
            # Create one-time invite link
            invite_link = await StripePaymentHandler.create_telegram_invite_link(
                expire_seconds=3600  # 1 hour expiration
            )
            
            # Store the invite link for retrieval
            StripePaymentHandler.store_invite_link(payment_id, invite_link)
            
            logger.info(f"Successfully processed payment {payment_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error handling payment success: {e}")
            return False


@app.route('/webhook/stripe', methods=['POST'])
def stripe_webhook():
    """
    Webhook endpoint for Stripe payment events.
    """
    payload = request.get_data()
    sig_header = request.headers.get('Stripe-Signature')
    
    # Verify webhook signature
    if not StripePaymentHandler.verify_webhook_signature(payload, sig_header):
        return {'error': 'Invalid signature'}, 400
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        return {'error': str(e)}, 400
    except stripe.error.SignatureVerificationError as e:
        return {'error': str(e)}, 400
    
    # Handle payment success event
    if event['type'] == 'payment_intent.succeeded':
        # Run async handler
        run_async(StripePaymentHandler.handle_payment_success(event))
        return {'status': 'success'}, 200
    
    return {'status': 'received'}, 200


@app.route('/create-payment-intent', methods=['POST'])
def create_payment_intent():
    """
    Create a Stripe payment intent.
    Expects JSON: {
        "amount": 5000 (in cents),
        "currency": "usd"
    }
    """
    try:
        data = request.json
        
        # Create payment intent without user_telegram_id
        intent = stripe.PaymentIntent.create(
            amount=data['amount'],
            currency=data['currency']
        )
        
        return {
            'client_secret': intent['client_secret'],
            'payment_id': intent['id']
        }, 200
    except Exception as e:
        logger.error(f"Error creating payment intent: {e}")
        return {'error': str(e)}, 400


@app.route('/payment-success/<payment_id>', methods=['GET'])
def payment_success(payment_id):
    """
    Display the success page with the Telegram group invite link.
    """
    invite_link = StripePaymentHandler.get_invite_link(payment_id)
    
    # If no invite link exists, verify payment and generate one
    if not invite_link:
        try:
            # Verify the payment was successful
            payment_intent = stripe.PaymentIntent.retrieve(payment_id)
            
            if payment_intent.status != 'succeeded':
                return render_template_string("""
                <!DOCTYPE html>
                <html>
                <head>
                    <title>Payment Status</title>
                    <style>
                        body {
                            font-family: Arial, sans-serif;
                            display: flex;
                            justify-content: center;
                            align-items: center;
                            height: 100vh;
                            margin: 0;
                            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        }
                        .container {
                            background: white;
                            padding: 40px;
                            border-radius: 10px;
                            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
                            text-align: center;
                            max-width: 500px;
                        }
                        .error-icon {
                            font-size: 60px;
                            margin-bottom: 20px;
                        }
                        h1 {
                            color: #e74c3c;
                            margin-bottom: 20px;
                        }
                        p {
                            color: #666;
                            line-height: 1.6;
                        }
                    </style>
                </head>
                <body>
                    <div class="container">
                        <div class="error-icon">⏳</div>
                        <h1>Payment Processing</h1>
                        <p>Your payment is being processed. Please refresh this page in a few moments.</p>
                        <p><small>Payment ID: {{ payment_id }}</small></p>
                        <p><small>Status: {{ status }}</small></p>
                    </div>
                </body>
                </html>
                """, payment_id=payment_id, status=payment_intent.status), 202
            
            # Payment successful, generate invite link
            logger.info(f"Payment {payment_id} verified as successful, generating invite link")
            invite_link = run_async(StripePaymentHandler.create_telegram_invite_link(expire_seconds=3600))
            StripePaymentHandler.store_invite_link(payment_id, invite_link)
            logger.info(f"Invite link generated and stored for payment {payment_id}")
            
        except stripe.error.InvalidRequestError as e:
            logger.error(f"Invalid payment ID {payment_id}: {e}")
            return render_template_string("""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Payment Not Found</title>
                <style>
                    body {
                        font-family: Arial, sans-serif;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        height: 100vh;
                        margin: 0;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    }
                    .container {
                        background: white;
                        padding: 40px;
                        border-radius: 10px;
                        box-shadow: 0 10px 40px rgba(0,0,0,0.1);
                        text-align: center;
                        max-width: 500px;
                    }
                    .error-icon {
                        font-size: 60px;
                        margin-bottom: 20px;
                    }
                    h1 {
                        color: #e74c3c;
                        margin-bottom: 20px;
                    }
                    p {
                        color: #666;
                        line-height: 1.6;
                    }
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="error-icon">❌</div>
                    <h1>Payment Not Found</h1>
                    <p>We couldn't find this payment. Please contact support if you believe this is an error.</p>
                    <p><small>Payment ID: {{ payment_id }}</small></p>
                </div>
            </body>
            </html>
            """, payment_id=payment_id), 404
        except Exception as e:
            logger.error(f"Error generating invite link for payment {payment_id}: {e}")
            return render_template_string("""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Error</title>
                <style>
                    body {
                        font-family: Arial, sans-serif;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        height: 100vh;
                        margin: 0;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    }
                    .container {
                        background: white;
                        padding: 40px;
                        border-radius: 10px;
                        box-shadow: 0 10px 40px rgba(0,0,0,0.1);
                        text-align: center;
                        max-width: 500px;
                    }
                    .error-icon {
                        font-size: 60px;
                        margin-bottom: 20px;
                    }
                    h1 {
                        color: #e74c3c;
                        margin-bottom: 20px;
                    }
                    p {
                        color: #666;
                        line-height: 1.6;
                    }
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="error-icon">⚠️</div>
                    <h1>Error Generating Invite Link</h1>
                    <p>There was an error generating your Telegram invite link. Please contact support.</p>
                    <p><small>Payment ID: {{ payment_id }}</small></p>
                    <p><small>Error: {{ error }}</small></p>
                </div>
            </body>
            </html>
            """, payment_id=payment_id, error=str(e)), 500
    
    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Payment Successful!</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
                margin: 0;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            }
            .container {
                background: white;
                padding: 40px;
                border-radius: 10px;
                box-shadow: 0 10px 40px rgba(0,0,0,0.1);
                text-align: center;
                max-width: 500px;
            }
            .success-icon {
                font-size: 80px;
                margin-bottom: 20px;
            }
            h1 {
                color: #27ae60;
                margin-bottom: 20px;
            }
            p {
                color: #666;
                line-height: 1.6;
                margin-bottom: 30px;
            }
            .invite-link {
                display: inline-block;
                background: #0088cc;
                color: white;
                padding: 15px 30px;
                border-radius: 5px;
                text-decoration: none;
                font-size: 18px;
                font-weight: bold;
                margin-top: 20px;
                transition: background 0.3s;
            }
            .invite-link:hover {
                background: #006699;
            }
            .warning {
                margin-top: 30px;
                padding: 15px;
                background: #fff3cd;
                border-left: 4px solid #ffc107;
                color: #856404;
                font-size: 14px;
            }
            .payment-id {
                margin-top: 20px;
                font-size: 12px;
                color: #999;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="success-icon">✅</div>
            <h1>Payment Successful!</h1>
            <p>Thank you for your purchase. Your payment has been processed successfully.</p>
            <p>Click the button below to join the Telegram group:</p>
            <a href="{{ invite_link }}" class="invite-link" target="_blank">Join Telegram Group</a>
            <div class="warning">
                ⚠️ This link expires in 1 hour and can only be used once. Please join now!
            </div>
            <div class="payment-id">
                Payment ID: {{ payment_id }}
            </div>
        </div>
    </body>
    </html>
    """, invite_link=invite_link, payment_id=payment_id)


@app.route('/check-payment-status/<payment_id>', methods=['GET'])
def check_payment_status(payment_id):
    """
    API endpoint to check if invite link is ready for a payment.
    """
    invite_link = StripePaymentHandler.get_invite_link(payment_id)
    
    if invite_link:
        return jsonify({
            'status': 'ready',
            'invite_link': invite_link
        }), 200
    else:
        return jsonify({
            'status': 'processing'
        }), 202


if __name__ == '__main__':
    # Get port from environment variable for deployment
    port = int(os.environ.get('PORT', 5000))
    
    # Run Flask app
    # Set debug=False for production!
    app.run(host='0.0.0.0', port=port, debug=False)
