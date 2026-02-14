# 🚀 Serverless Setup - No Server Management!

## ✅ Easiest Option: Stripe Payment Link + Webhook

This approach requires NO server management - just a simple webhook function.

---

## 📋 Setup Steps

### Step 1: Create Stripe Payment Link

1. Go to https://dashboard.stripe.com/payment-links
2. Click **"+ New"**
3. Configure your product:
   - **Name**: Premium Telegram Group Access
   - **Price**: $1.00 USD
   - **Description**: Lifetime access to exclusive group
4. Click **"Create link"**
5. Copy your payment link (looks like: `https://buy.stripe.com/xxxxx`)

**That's your checkout page! No coding needed.**

---

### Step 2: Deploy Serverless Webhook (Choose One Platform)

#### Option A: Netlify (Recommended - Easiest)

1. **Create Netlify account**: https://netlify.com
2. **Create new site** from your GitHub repo: https://github.com/raiderromero/tglinkpayment
3. **Add build settings**:
   - Build command: `pip install -r requirements.txt`
   - Publish directory: `.`
4. **Add Environment Variables** (Site settings → Environment variables):
   ```
   STRIPE_SECRET_KEY=sk_live_51KLeU...
   TELEGRAM_BOT_TOKEN=8227364388:AAH...
   TELEGRAM_GROUP_ID=-1003798603747
   STRIPE_WEBHOOK_SECRET=(get from Step 3)
   ```
5. **Create webhook function**:
   - Create folder: `netlify/functions/`
   - Add file: `webhook.py` (use netlify_function.py content)
6. Your webhook URL will be: `https://yoursite.netlify.app/.netlify/functions/webhook`

#### Option B: Vercel

1. **Create Vercel account**: https://vercel.com
2. **Import Git Repository**: https://github.com/raiderromero/tglinkpayment
3. **Add Environment Variables** (Settings → Environment Variables):
   - Same as Netlify above
4. **Create API route**:
   - Create folder: `api/`
   - Add file: `webhook.py`
5. Your webhook URL will be: `https://yourproject.vercel.app/api/webhook`

---

### Step 3: Configure​ Stripe Webhook

1. Go to https://dashboard.stripe.com/webhooks
2. Click **"+ Add endpoint"**
3. **Endpoint URL**: Your serverless function URL from Step 2
   - Netlify: `https://yoursite.netlify.app/.netlify/functions/webhook`
   - Vercel: `https://yourproject.vercel.app/api/webhook`
4. **Select events to listen to**:
   - Click "Select events"
   - Check: `checkout.session.completed`
   - Click "Add events"
5. Click **"Add endpoint"**
6. **Copy the Signing secret** (starts with `whsec_`)
7. Add this to your environment variables as `STRIPE_WEBHOOK_SECRET`

---

### Step 4: Configure Success Page

1. Upload `success_static.html` to your website
2. Edit the file and update:
   ```javascript
   const WEBHOOK_URL = 'https://your-actual-site.netlify.app/.netlify/functions/webhook';
   ```
3. In Stripe Payment Link settings:
   - Go to your payment link
   - Click "Edit"
   - Under "After payment" → "Custom success page"
   - Enter: `https://yourdomain.com/success_static.html?payment_intent={CHECKOUT_SESSION_ID}`

---

## 🎯 How It Works

1. **Customer clicks** your Stripe Payment Link
2. **Stripe processes payment** → Redirects to your success page
3. **Stripe sends webhook** to your serverless function
4. **Function generates** Telegram invite link
5. **Success page polls** for the invite link
6. **Customer sees** the Telegram link and joins!

---

## ✅ Advantages

- ✅ **No server management** - Netlify/Vercel handles everything
- ✅ **Auto-scaling** - Handles any traffic
- ✅ **Free tier available** - Both platforms have generous free tiers
- ✅ **SSL included** - Automatic HTTPS
- ✅ **Simple deployment** - Push to Git and deploy
- ✅ **No code checkout** - Just share the Stripe Payment Link

---

## 💰 Costs

### Netlify Free Tier:
- 100GB bandwidth/month
- 300 build minutes/month
- 125k function executions/month
- **Perfect for this use case!**

### Vercel Free Tier:
- 100GB bandwidth/month
- 100 hours serverless function execution
- **Also perfect!**

Both are FREE for most use cases.

---

## 🧪 Testing

1. **Test Payment**:
   - Use your Stripe Payment Link
   - Use test card: `4242 4242 4242 4242`
   - Check webhook logs in Stripe dashboard
   
2. **Test Webhook**:
   - Stripe dashboard → Webhooks → Your endpoint
   - Click "Send test webhook"
   - Select `checkout.session.completed`
   - Check function logs in Netlify/Vercel

---

## 📱 Your Final Setup

1. **Checkout**: Stripe Payment Link (no coding!)
2. **Payment Processing**: Stripe (automatic)
3. **Webhook**: Serverless function on Netlify/Vercel
4. **Success Page**: Static HTML on your website
5. **Telegram Bot**: Generates invite links

**Total coding needed**: Just one webhook function!

---

## 🚀 Quick Start Command

For Netlify:
```bash
# In your repo folder
mkdir -p netlify/functions
cp netlify_function.py netlify/functions/webhook.py
git add .
git commit -m "Add webhook function"
git push origin main
```

Then connect your GitHub repo to Netlify and you're done!

---

**This is 10x easier than managing a full Flask app!** 🎉
