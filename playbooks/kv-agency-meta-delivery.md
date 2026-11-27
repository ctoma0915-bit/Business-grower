# KV Agency: Meta delivery for one new client

The product: the client pays 197 € once, KV pays the ads, then 5% of each job that came through us. Promise: 10 requests for quotes in the first 30 days of ads, or the 197 € back.

Numbers come from both Meta ad accounts, as of 27 Nov 2026. "Untested" means Toma hasn't tried it yet. Form and ad texts are in `meta-lead-form.md`.

## 1. What we need from the client for Meta

1. Facebook page and Instagram: add Toma as admin in Business Suite.
2. 10–20 photos of their own jobs: finished, before/after, team at work.
3. Up to 4 services to advertise, plus the area (towns or county).
4. The WhatsApp number where requests arrive, and a promise to call each one within 15 minutes.
5. Firm name, CUI, address and email, for the privacy page.

## 2. Day 0 → ads live in 3 working days

Each step: day · who · what · done when.

1. D0 · client · pays 197 € and sends the 5 items · done when all 5 are in the chat.
2. D0 · client · adds Toma to the page and Instagram · done when the page shows in our ad tools.
3. D0 · KV · builds the privacy page and 4–5 ad images (1080×1350) from their photos · done when the privacy link opens.
4. D1 · Toma (or the client) · creates the Instant Form from the `meta-lead-form.md` texts and accepts the Lead Ads Terms · done when we have the form ID.
5. D1 · KV · sets up the hub prefix (EE) and the form → hub → WhatsApp route, then sends a test lead · done when the test gets EE-001 on the client's WhatsApp (**untested**).
6. D1 · client · turns on lead notifications in the Business Suite app · done when the test lead pings their phone.
7. D2 · KV · builds the campaign, ad set and ads, all paused · done when every preview is right.
8. D2 · KV → client · sends the approval text (section 6) · done when the client replies "DA".
9. D3 · KV · activates · done when the ads are approved, active and spending.
10. D3+ · client · calls or WhatsApps each request within 15 minutes · done when every code is marked "contacted".

## 3. Budget (1 € ≈ 5 lei)

- **Start:** 15 lei/day ≈ 450 lei/month (≈ 90 €). Tested on 3 clients.
- **București-size area:** 20 lei/day ≈ 600 lei/month (≈ 120 €). Tested.
- **Ceiling:** 25 lei/day ≈ 750 lei/month (≈ 150 €). Tested on 1 client. Above that is **untested**.
- **Real cost:** 17.5 lei per request on average (87 requests, 5 clients, Nov 2026). Range 16–23 lei.
  - So 15 lei/day ≈ 20–28 requests a month, against the 10 promised.
  - First-month ads take about half the 197 €.
- **Split:** Toma runs no separate test budget.
  - Days 1–7 (test): the whole budget on 4–5 ads in one ad set.
  - Days 8–30 (scale): the same ad set with the losers paused.
  - Add 5 lei/day only if a request costs 20 lei or less and the client calls back fast, with Toma's OK.
  - Separate test and scale ad sets: **untested**.

## 4. Targeting + creative

- Objective Leads, form inside Facebook, button "Obțineți ofertă". Tested.
- Area: their towns or county (e.g. BUC+Ilfov, Oradea+Bihor). Whole country only if they really travel, and then add City to the form. Tested.
- Age 25+, Advantage+ audience and placements, no interests. Tested.
- 4–5 ads in one ad set, 1080×1350 images, their own photos first. Tested.
- **Best angle everywhere** is the leak ("Vă plouă în casă?", "Infiltrații"): 10.5–16.5 lei per request. Use it in 2 ads.
- **Weaker angles:** "Înainte de iarnă" (24–52 lei per request); the review ad got 0 requests on 17 lei. Use at most 1 of these.
- Video: one test, 3 requests for 11 lei. Too small to judge.
- 9:16 Stories/Reels versions: **untested**.
- Stock photos only as illustration, never "lucrarea noastră". Tested: 13 requests at one client.
- **Never in ads:** prices, discounts, guarantees, years in business.
- Euro Tetto's live ad "ET 3" shows "Garanție extinsă". Don't copy it.

## 5. Lead route

**Use the Instant Form.** It is tested: 87 requests at ≈ 17.5 lei each.
- WhatsApp ads: 33 lei spent, no chats measured.
- Ads to a site: never properly run (**untested**).

**Site form:** keep it for traffic that doesn't come from Meta. It already saves each request with a code and emails Toma (tested on Nord Roof).

**Meta lead → code → hub → WhatsApp (untested):**
1. Make.com (free plan): Facebook Lead Ads "Watch New Leads" on the client's form.
2. Make posts the lead to the same hub script as the site form, tagged "Meta". The hub gives the next code (EE-014).
3. Make sends the client a WhatsApp with the code, name, phone, answer and town.

**Backup, works today:** Leads Center plus app notifications on the client's phone. Toma checks Leads Center twice a day and adds codes by hand.

## 6. Approval text (sent before launch)

```
Bună ziua! Reclamele [FIRMA] pentru Facebook și Instagram sunt gata: [LINK].
Fără prețuri, reduceri sau garanții: doar lucrările dumneavoastră, zona [ZONA] și „Obțineți ofertă”.
Fiecare cerere vă vine pe WhatsApp cu un cod (ex. EE-001); sunați clientul în 15 minute. Scrieți „DA” și pornim.
```

## 7. Day 15: under 5 requests

At 15 lei/day, day 15 should show 10–14. Under 5 means something is broken. Fix in this order:

1. **Delivery:** under 180 lei spent? Fix rejected ads or payment, and re-activate if a budget edit paused the campaign.
2. **Count:** compare Leads Center with the hub. Missing codes mean the route is broken, not the ads.
3. **Pause losing ads** with the 3× rule, keep the best one. Tested.
4. **Add 2 new leak ads** with new photos of their own jobs. Tested angle.
5. **Widen the area:** town → county → neighbouring counties (**untested** as a fix).
6. **Go to 25 lei/day** for days 16–30, with Toma's OK. Tested on 1 client.

## 8. Weekly numbers to report

1. Spend: this week and total.
2. Requests with a code: this week and total, against 10 in 30 days.
3. Cost per request: target 20 lei or less.
4. Jobs won from codes, for the 5% (client-reported, **untested**).

## 9. Kill/pause rules

- Pause ads that cost 3× the best ad. Pause, never delete. Tested.
- Pause at once if page access is removed, payment fails or ads are rejected twice. Restart when fixed.
- Pause if the client leaves a request without contact for 24 h, or 3 in one week (**untested**).
- Pause the campaign if a request costs over 45 lei after 7 days and at least 150 lei spent (**untested** threshold).
- Day 30 under 10 requests: refund the 197 € under the terms and stop (**untested**).
- After day 30: stop after 60 days with no job won (≈ 900 lei spent), or if the client won't confirm jobs by code (**untested**).
