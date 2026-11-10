"""Generates data/tickets.json (80 sample tickets) and data/test_tickets.json (20 held-out tickets)."""
import json, os, random
from datetime import datetime, timedelta
random.seed(7)
D = os.path.dirname(os.path.abspath(__file__))
NAMES = ["Aarav Mehta","Priya Nair","Rohan Gupta","Sneha Rao","Vikram Singh","Ananya Iyer","Kabir Shah","Meera Joshi","Arjun Reddy","Ishita Das","Dev Malhotra","Tara Bose","Nikhil Verma","Zoya Khan","Rahul Sinha"]
B = {
 "billing": [("Charged twice this month","Hi, I was charged twice for my subscription this month. Please refund the extra payment."),
  ("Invoice missing GST details","Our finance team needs the invoice to include our GST number. Can you reissue the invoice?"),
  ("Refund not received","I cancelled last week and still no refund on my credit card. Please check the payment."),
  ("Wrong price on billing page","The billing page shows a higher price than what we agreed. Please correct the charge.")],
 "bug": [("Export to CSV crashes","The export button crashes the app with an error every time I click it on the reports page."),
  ("App not working after update","Since the update the app is broken, it keeps failing on launch with a timeout error."),
  ("Search is very slow","Search takes 30 seconds and sometimes fails with a timeout. This looks like a bug."),
  ("Webhook not firing","Our webhook stopped firing and nothing is delivered. Looks like a bug on your side.")],
 "feature_request": [("Dark mode please","It would be great if you could add dark mode. Many of our team work at night."),
  ("Slack integration","Feature request: please add a Slack integration for notifications."),
  ("Bulk edit option","Can you add an option to bulk edit tags? Would be nice to have."),
  ("Support for Okta SSO","We would like support for Okta SSO. Is this on the roadmap? Suggestion for a future release.")],
 "account_access": [("Cannot log in","I can't log in since yesterday, it says my account is locked."),
  ("2FA code not arriving","The verification code for two-factor never arrives so I cannot sign in."),
  ("Locked out after password change","I changed my password and now I am locked out. Please help."),
  ("Account suspended?","My login shows account suspended. I need access.")],
 "how_to": [("How do I invite teammates?","Hi, how do I invite new teammates to my workspace?"),
  ("How to set up a custom domain","Where can I find the steps to set up a custom domain? Looking for a guide."),
  ("How can I export old reports","How can I download reports from last year? Is it possible to schedule exports?"),
  ("How to configure notifications","How do I configure email notifications for my team?")],
}
SPECIAL = [  # Hinglish, typos, and the "angry free tweet vs polite enterprise email" curveball
 ("billing","Payment kat gaya par plan active nahi","Mera paisa kat gaya lekin subscription active nahi hua, refund chahiye.","pro","chat"),
 ("bug","App kaam nahi kar raha","Hamara dashboard kaam nahi kar raha, error aa raha hai.","free","chat"),
 ("account_access","Login nahi ho raha","Password bhool gaya, login nahi ho raha, access nahi mil raha.","free","email"),
 ("how_to","Team member ko kaise add karein","Naye user ko kaise add karein? Guide chahiye.","pro","chat"),
 ("account_access","Cant login to my acount","pasword reset email never comes, locked out","free","email"),
 ("billing","Chargd twice","I was chargd twise on my invocie, plese refnd","pro","email"),
 ("bug","App crashs when uploding","the app crashs everytime i upload, error 500","free","chat"),
 ("bug","@yottaflex your app is garbage","This is the worst, third time the export crashed and nobody replies!!! Useless!!!","free","twitter"),
 ("bug","Minor issue with report formatting","Hello team, when convenient, the report footer looks slightly misaligned. Thanks!","enterprise","email"),
]
base = datetime(2026, 1, 5, 9, 0); rows = []
def add(cat, s, b, tier, ch, ts, name=None):
    rows.append({"ticket_id": f"T-{1001+len(rows)}", "customer_name": name or random.choice(NAMES), "plan_tier": tier, "subject": s, "body": b,
                 "created_at": ts.isoformat(timespec="seconds"), "channel": ch, "true_category": cat})
for _ in range(58):
    c = random.choice(list(B)); s, b = random.choice(B[c])
    add(c, s, b, random.choices(["free","pro","enterprise"], [5,3,2])[0], random.choice(["email","chat","email","twitter"]), base + timedelta(minutes=random.randint(0, 420)))
for k, (c, s, b, tier, ch) in enumerate(SPECIAL):
    add(c, s, b, tier, ch, base + timedelta(minutes=300 + k * 12), name="Zoya Khan" if k == 7 else None)
burst = [("Dashboard not loading","Our dashboard is not loading and shows a 500 error. Production work is blocked."),
         ("Getting 500 error on dashboard","The dashboard shows a 500 error, not loading since a few minutes. Everyone on my team is blocked."),
         ("Dashboard down","Dashboard is down, 500 error and not loading. Production is blocked."),
         ("500 error, dashboard not loading","Dashboard not loading with 500 error since morning, our team is blocked.")]
for k in range(13):
    s, b = burst[k % 4]; add("bug", s, b, random.choices(["free","pro","enterprise"], [3,4,3])[0], random.choice(["email","chat","twitter"]), base + timedelta(minutes=450 + k * 2))
json.dump(rows, open(os.path.join(D, "tickets.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)

TEST = [("billing","Unexpected deduction on my card","There is a charge on my card I don't recognise, refund this please."),
 ("billing","Need a receipt for last quarter","Please send the receipt and invoice for the payment made in March."),
 ("bug","Upload fails with error","File upload fails every time with error 413, broken since Monday."),
 ("bug","Page is not loading","The reports page is not loading and the spinner is stuck."),
 ("bug","App crashing on iPad","It crashes immediately when I open it."),
 ("feature_request","Suggestion: calendar sync","It would be nice to have a Google Calendar integration."),
 ("feature_request","Wish list","Please add support for exporting to PDF."),
 ("feature_request","Custom fields","Can you add custom fields to the contact form? Feature request."),
 ("account_access","Unable to sign in","I cannot access my account, getting a locked message."),
 ("account_access","OTP not received","The otp never arrives on my phone when I sign in."),
 ("account_access","Reset link expired","My password reset link expired and I'm locked out."),
 ("how_to","How to add a new project?","How do I add a new project and set up folders?"),
 ("how_to","Where can I find API docs?","Where can I find the guide for the API? Looking for a tutorial."),
 ("how_to","Steps to enable reports","What are the steps to turn on weekly reports? How can I schedule them?"),
 ("other","Partnership inquiry","We run an agency and would like to discuss partnership opportunities."),
 ("other","Thank you!","Just wanted to say the team was lovely last week."),
 ("bug","Report download nahi ho raha","Report download nahi chal raha, error aa raha hai bug lagta hai."),
 ("billing","Refund kab milega","Mera paisa wapas chahiye, invoice bhi bhejiye."),
 ("account_access","Cant sing in","pasword not working, acount locked"),
 ("how_to","Invoice kaise download karein","Invoice kaise download karein? Guide chahiye.")]
json.dump([{"subject": s, "body": b, "true_category": c} for c, s, b in TEST], open(os.path.join(D, "test_tickets.json"), "w"), indent=1)
print(len(rows), "tickets,", len(TEST), "test tickets")
