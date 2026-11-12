# Meta lead form ads (Instant Forms): reusable playbook

Use this for any client who wants requests from Facebook and Instagram ads: roofing, windows, renovations or any local service. Replace every `[PLACEHOLDER]` with the client's details. Write the form texts in Romanian, exactly as below.

## Why form ads

In our first test for a local service business (2026), form ads clearly beat WhatsApp ads:
- **Form ads:** 15 requests for about 130 lei. The best ad cost about 5 lei per request.
- **WhatsApp ads:** people tapped them, but almost nobody started a chat.

So start new clients on form ads. Add WhatsApp ads only as a small extra, if at all.

## 1. Fill in these details first

| Placeholder | Example |
|---|---|
| `[FIRMA]` | name of the client's page |
| `[SERVICII]` | Reparații, infiltrații, acoperiș nou, jgheaburi |
| `[ZONA]` | București și Ilfov / toată România |
| `[OFERTA]` | Evaluare gratuită la fața locului |
| `[TELEFON]` | +40 7xx xxx xxx |
| `[LINK_CONFIDENTIALITATE]` | a public privacy page (we can host it on this repo's GitHub Pages) |

## 2. Create the form (the client does this; our Meta tools can't)

**Goal:** the person taps the ad, sees their name and phone already filled in, taps one answer and sends, with nothing to type and nothing to think about. Every extra screen, field or long text loses people.

Create it in **business.facebook.com → All tools → Instant forms → Create form**. If Meta asks, accept the **Lead Ads Terms**.

**Changing a form:** once published, a form can't be edited. Open the list of forms, choose **Duplicate**, change the copy, publish it, then move the ads to the new form ID.

**Form name** (only the client sees it): `[FIRMA] · Ofertă rapidă`

**Form type:** **More volume** ("Volum mai mare").
- **Why:** sending is one tap, with no extra review screen.
- **The cost:** a few more wrong numbers. Calling every lead within 15 minutes covers that.
- **When to switch:** use **Higher intent** only if more than about 1 in 4 numbers turn out wrong.

**Intro:** turn it **off**, so the form opens straight on the questions. If Meta insists on an intro, use only the ad image and the headline `Ofertă gratuită în 5 secunde`, with no description.

**Questions description** (the line above the questions; this is what removes doubt):
```
✅ Gratuit și fără obligații
✅ Numele și telefonul sunt deja completate
👉 Alegeți o variantă și apăsați Trimiteți
```

**Questions**, in this order:
1. **Custom question → Multiple choice:** `Cu ce vă putem ajuta?`.
   - Write the answers the way customers talk ("my roof leaks"), not in trade terms.
   - Use 4 answers at most.

   | Trade | Answers |
   |---|---|
   | Roofing | `Îmi intră apa în casă` · `Acoperiș nou sau înlocuire` · `Reparație la acoperiș` · `Jgheaburi și burlane` |
   | Windows | `Ferestre noi` · `Schimb ferestrele vechi` · `Ușă de exterior` · `Reparație / reglaj` |
   | Renovations | `Renovare completă` · `Baie sau bucătărie` · `Zugrăveli și finisaje` · `Altă lucrare` |
2. **Prefill questions:**
   - **Full name** and **Phone number**. Meta fills both in from the person's profile.
   - **National clients only:** also add **City** ("Oraș"). It is prefilled too, so it costs no typing.
   - **Local clients:** don't ask for the location. The ad's targeting already covers the area; ask for the address on the call.
   - Don't add email, budget, dates or any field people have to type.

**Privacy policy**
- Link text: `Politica de confidențialitate`
- Link: `[LINK_CONFIDENTIALITATE]`

**Ending screen**
- **Headline:** `Gata! Am primit cererea ✅`
- **Description:** `Vă sunăm noi astăzi, de pe [TELEFON]. Nu mai trebuie să faceți nimic.`
  Promise "astăzi" only if the client really calls the same day.
- **Button:** **Call business**, text `Sunați-ne acum`, number `[TELEFON]`.

**Settings:** language Romanian; sharing **Restricted**.

**Contact information:** the form doesn't need a field for this. The client's phone goes on the ending button and in the ending text. A WhatsApp text works as the first contact.

When it's published, ask the client for the **form ID**. Ads can't be created without it.

**Ad text:** end it with the same promise as the form, for example:
```
👉 Apăsați „Obțineți ofertă”: numele și telefonul se completează singure. Durează 5 secunde, gratuit și fără obligații.
```

## 3. Build the ads (Meta Ads tools)

**Campaign**
- **Objective:** leads.
- **Keep it separate:** a form campaign can't share a campaign with WhatsApp ads.
- **Overlapping clients:** clients in the same trade and area each get their own campaign, form and lead codes.

**Ad set**
- Optimization **LEAD_GENERATION**, destination **ON_AD**.
- The client's page, the Instagram account if connected, and the radius or regions of `[ZONA]`.

**Creative**
- `link_data.link`: `"http://fb.me/"`.
- `call_to_action`: `{"type":"GET_QUOTE","value":{"lead_gen_form_id":"<FORM ID>"}}`.
- Without the form ID, the ad fails with "Missing Lead Form".
- Ads can't switch forms. To move to a new form, create new ads with the same image and the new form ID, then pause the old ads once the new ones deliver.

**Ads**
- Make 3 to 5, each with a different photo and angle: a problem like leaks, a finished job, a review, a seasonal hook like "before winter", and a price or free visit.
- Use the client's real photos.

**Budget**
- **Amounts:** budgets are in minor units (2000 = 20 lei/day). Start at 15 to 20 lei/day.
- **After editing:** changing a budget can pause the campaign. Check it's active again afterwards.

**Launch:** create everything paused, check the preview, then activate.

## 4. Handling the leads

**Where they appear**
- Requests only appear in **Meta Business Suite → Leads Center**.
- Meta doesn't email them, and our Meta tools can't read them.
- Tell the client to turn on lead notifications in the Business Suite app.
- To work on leads in a chat, paste a screenshot or the Leads Center download.

**Automatic copy into a sheet (optional, free)**
- Make.com: **Facebook Lead Ads → Watch New Leads**, then **Google Sheets → Add a row** (or an HTTP request to the client's sheet).
- When Make.com asks for payment, choose the **Free** plan and don't start from a paid template. The free plan covers this volume.

**Speed:** contact each lead within minutes, on WhatsApp first. Leads go cold within hours.

**First WhatsApp message** (adapt it to the lead's answers):
```
Bună ziua, domnule/doamna [NUME]! Sunt [PRENUME], de la [FIRMA]. Ați completat formularul nostru pentru [LUCRARE]. Mulțumim!

Ca să vă putem da detalii și un preț corect, ne puteți trimite:
1. câteva poze cu [ZONA CU PROBLEMA / ce e de făcut]
2. [o întrebare despre lucrare, de ex. ce fel de acoperiș aveți / câte ferestre]
3. localitatea sau adresa aproximativă

[Evaluarea la fața locului este gratuită.] Ce zi și oră v-ar conveni să trecem?
```
Ask for photos and the address first, so the job can be priced before anyone travels.

## 5. Checking and optimizing

**When to judge:** check cost per request after 3 days. Meta usually pushes most of the budget to one ad.

**Weak ads:**
- **When to pause:** an ad has spent at least 3× the best ad's cost per request and costs at least 3× as much per request.
- **Pause, never delete.**

**When the account changes:** if another chat edits the account, check the activity log before deciding.

**Budget moves:** report them and get the client's or Toma's OK before changing anything.
