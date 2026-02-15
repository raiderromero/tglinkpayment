// Netlify Serverless Function - Unban & Invite Link Generator
const https = require('https');

const TELEGRAM_BOT_TOKEN = process.env.TELEGRAM_BOT_TOKEN;
const TELEGRAM_GROUP_ID = process.env.TELEGRAM_GROUP_ID || '-1003798603747';
const TELEGRAM_API_URL = `https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}`;

// Helper to make HTTPS POST requests
function telegramApiCall(method, payload) {
  return new Promise((resolve, reject) => {
    const data = JSON.stringify(payload);
    const url = new URL(`${TELEGRAM_API_URL}/${method}`);
    
    const options = {
      hostname: url.hostname,
      path: url.pathname,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(data),
      },
    };

    const req = https.request(options, (res) => {
      let body = '';
      res.on('data', (chunk) => { body += chunk; });
      res.on('end', () => {
        try {
          resolve(JSON.parse(body));
        } catch (e) {
          reject(new Error(`Failed to parse response: ${body}`));
        }
      });
    });

    req.on('error', reject);
    req.setTimeout(10000, () => {
      req.destroy();
      reject(new Error('Request timed out'));
    });
    req.write(data);
    req.end();
  });
}

// CORS headers
const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'POST, GET, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type, Stripe-Signature',
  'Content-Type': 'application/json',
};

exports.handler = async (event, context) => {
  // Handle CORS preflight
  if (event.httpMethod === 'OPTIONS') {
    return {
      statusCode: 200,
      headers: corsHeaders,
      body: '',
    };
  }

  // Handle POST requests
  if (event.httpMethod === 'POST') {
    try {
      const body = JSON.parse(event.body || '{}');

      // Handle unban request
      if (body.action === 'unban') {
        const userId = body.user_id;

        if (!userId) {
          return {
            statusCode: 400,
            headers: corsHeaders,
            body: JSON.stringify({ success: false, message: 'user_id is required' }),
          };
        }

        console.log(`Sending unban request for user ${userId} to chat ${TELEGRAM_GROUP_ID}`);

        const result = await telegramApiCall('unbanChatMember', {
          chat_id: parseInt(TELEGRAM_GROUP_ID),
          user_id: parseInt(userId),
          only_if_banned: false,
        });

        console.log('Telegram API Response:', JSON.stringify(result));

        if (result.ok) {
          return {
            statusCode: 200,
            headers: corsHeaders,
            body: JSON.stringify({ success: true, message: 'User unbanned successfully' }),
          };
        }

        const errorDesc = result.description || 'Unknown error';
        console.log('Telegram API error:', errorDesc);
        return {
          statusCode: 200,
          headers: corsHeaders,
          body: JSON.stringify({ success: false, message: `Failed to unban: ${errorDesc}` }),
        };
      }

      // Handle create invite link request
      if (body.action === 'create_invite') {
        const expireDate = Math.floor(Date.now() / 1000) + 3600;
        const result = await telegramApiCall('createChatInviteLink', {
          chat_id: parseInt(TELEGRAM_GROUP_ID),
          expire_date: expireDate,
          member_limit: 1,
        });

        if (result.ok) {
          return {
            statusCode: 200,
            headers: corsHeaders,
            body: JSON.stringify({ success: true, invite_link: result.result.invite_link }),
          };
        }

        return {
          statusCode: 200,
          headers: corsHeaders,
          body: JSON.stringify({ success: false, message: result.description || 'Failed to create invite link' }),
        };
      }

      // Default POST response
      return {
        statusCode: 400,
        headers: corsHeaders,
        body: JSON.stringify({ success: false, message: 'Unknown action. Use action: "unban" or "create_invite"' }),
      };

    } catch (e) {
      console.error('Error:', e.message);
      return {
        statusCode: 500,
        headers: corsHeaders,
        body: JSON.stringify({ success: false, message: e.message }),
      };
    }
  }

  // Handle GET requests (health check)
  if (event.httpMethod === 'GET') {
    return {
      statusCode: 200,
      headers: corsHeaders,
      body: JSON.stringify({
        status: 'healthy',
        bot_token_present: !!TELEGRAM_BOT_TOKEN,
        group_id: TELEGRAM_GROUP_ID,
        function: 'netlify_function',
      }),
    };
  }

  // Default response
  return {
    statusCode: 400,
    headers: corsHeaders,
    body: JSON.stringify({ error: 'Invalid request method' }),
  };
};
