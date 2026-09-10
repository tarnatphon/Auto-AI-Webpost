# LINE OA Setup Guide — for Luke Social Agency (LINE connector)

Time: ~10 minutes. End result: a Channel Access Token you paste into the app's LINE
connector (Social Agency v2.2) to broadcast posts to your followers.

Do this on your Mac, in order. Steps 1-6 are in the browser, steps 7-8 in Terminal.

## Part A — Create the Official Account + Messaging API channel (in browser)

1. Go to https://developers.line.biz/ and click Log in → scan the QR code with the LINE app
   on your phone (any LINE account works; use the one that owns the business).
2. On the console home, click Create a new provider (if asked). Provider = your company name
   (e.g. Luke Studio). Click Create.
   - If you ALREADY have a LINE Official Account: instead log in at https://manager.line.biz
     → your account → Settings → Messaging API → Enable Messaging API → choose/create the
     same provider. Then jump to step 5.
3. From the provider page, click Create a Messaging API channel.
4. Fill in: Channel name (shows as the account name), Channel description, email, and pick
   Thailand as the region → Create.
   - This automatically creates the linked LINE Official Account (the thing people add as
     a friend).
5. Open the channel → Messaging API tab.
6. Scroll to the bottom → Channel access token (long-lived) → click Issue → copy the token
   and keep it somewhere safe (Notes app / password manager). This is the only secret the
   app needs.
   - Nearby, also grab the QR code / Bot basic ID (same page, top section) and add the
     account as a friend from your phone's LINE — broadcasts only reach friends, so add
     yourself to be able to test.

## Part B — Recommended settings (same page, 1 minute)

7. In the Messaging API tab: set Auto-reply messages to Disabled (the default "Thank you!"
   auto-reply looks unprofessional). Greeting messages can stay on.
8. No webhook setup is needed — the app only sends broadcasts; it doesn't receive messages.

## Part C — Verify it works (Terminal on your Mac, replace YOUR_TOKEN with the real token)

9. Check the token + see your bot name (should return JSON with "displayName"):

```bash
curl -s -H "Authorization: Bearer YOUR_TOKEN" https://api.line.me/v2/bot/info
```

10. Check your remaining monthly message quota:

```bash
curl -s -H "Authorization: Bearer YOUR_TOKEN" https://api.line.me/v2/bot/message/quota
```

11. Send a real test broadcast (arrives in LINE on every phone that added the account —
    including yours):

```bash
curl -s -X POST -H "Authorization: Bearer YOUR_TOKEN" -H "Content-Type: application/json" -d '{"messages":[{"type":"text","text":"ทดสอบระบบจาก Luke Social Agency"}]}' https://api.line.me/v2/bot/message/broadcast
```

Expected response: `{"sentMessages":[...],...}` — and the message appears in LINE within seconds.

## Part D — When Social Agency v2.2 is running

12. Social Agency → header gear icon (Connectors) → LINE → paste the Channel Access Token →
    Test connection (shows your OA name) → send one Test post → then switch the connector
    from dry-run to live. Done — scheduled posts broadcast automatically.

## Notes

- Quota: broadcasts count against the OA plan's monthly message allowance (free
  Communication plan ≈ 200-500 messages/month depending on region; a broadcast to N friends
  consumes N messages). Check usage anytime with the step-10 command or in LINE OA Manager →
  Home. The app checks this automatically before sending.
- Token safety: it never expires, but clicking Reissue in the console kills the old one —
  if you ever reissue, paste the new token into the app. Never share it; anyone with it can
  message your followers.
- Not possible via official API: posting to a personal LINE timeline or a group chat.
  Broadcasts to your OA's friends is the official, supported path.
- Per client: each client business follows this guide once with their own LINE account and
  pastes their token into their own client's connector.
