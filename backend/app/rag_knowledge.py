"""
RAG KNOWLEDGE BASE
------------------
Curated, grounded knowledge about THIS fraud-detection system: common issues an
admin may hit, how to diagnose them, and exactly what to do to fix them.

Every entry is written from the actual implementation (see ml_risk.py,
behaviour_ai.py, graph_engine.py, investigator.py, verification.py,
feedback.py, pipeline.py, main.py) so the RAG answers are specific and
actionable rather than generic consultancy advice.

`questions` are natural phrasing hints used for TF-IDF retrieval matching.
"""

# A small helper describing the decision thresholds / review band, shared by
# several entries so admins can ask about how decisions are made.
_DECISION_CAVEAT = (
    "Decisions come from the AI Investigator ensemble: block when the combined "
    "fraud probability >= 0.80, review when >= 0.44, else approve. Medium-risk "
    "(review) payments are never auto-declined: they are held for phone-call "
    "payment confirmation (OTP + call script) and settle only after the payer "
    "confirms ownership."
)

KNOWLEDGE = [
    {
        "id": "false_positive_surge",
        "title": "False-positive surge (legit payments blocked/reviewed)",
        "severity": "high",
        "tags": ["false positive", "false_positive", "legit", "legitimate", "blocked",
                 "review surge", "friction", "customer"],
        "questions": [
            "why are legitimate payments being blocked",
            "false positives surge legit customers blocked",
            "good customers getting reviewed",
            "why is a clean payment flagged",
            "high friction on legitimate users",
        ],
        "description": "Legitimate payers are being blocked or sent to review",
        "diagnosis": (
            "Open the payment stream (Recent payments) and sort by risk. Filter "
            "to block/review and inspect the evidence: which model fired and why. "
            "Watch for review-band escalation: any payment with behaviour anomaly "
            f"p_behaviour >= 0.9 AND amount >= Rs 1000 is auto-escalated to review "
            "even if the ensemble risk is low. On a clean held-out set this system "
            "achieves 0 false positives, so a persistent false-positive surge usually "
            "means either an over-sensitive behaviour autoencoder, a new legit "
            "customer with no history (high anomaly), or a recent retrain that "
            "shifted the boundary."
        ),
        "remedy": (
            "1) Check /api/test-metrics: if false positives > 0 on the held-out set, "
            "re-train with the baseline seed (python train.py) to restore the "
            "0-false-positive boundary. 2) Raise approve_thresh/review_thresh in "
            "Investigator only after confirming real fraud still gets caught. "
            "3) If one legitimate population is being reviewed, add more clean "
            "examples for it and retrain. 4) Confirm the behaviour anomaly guard "
            "(p_behaviour >= 0.9 AND amount >= 1000) is only catching genuinely "
            "novel high-value behaviour. 5) Reduce customer friction by ensuring "
            "review-band payments settle promptly via phone verification."
        ),
    },
    {
        "id": "false_negatives",
        "title": "False negatives (fraud approved)",
        "severity": "critical",
        "tags": ["false negative", "false_negative", "fraud approved", "leak",
                 "chargeback", "missed", "leakage"],
        "questions": [
            "fraudulent payment got approved",
            "why did fraud slip through",
            "false negatives leak fraud approved",
            "chargeback happening",
            "fraud not blocked",
        ],
        "description": "A fraudulent payment was approved (leaked)",
        "diagnosis": (
            "On the held-out set recall is 0.973 with 5 false negatives (all "
            "review-band, never approved outright). A live false negative usually "
            "means the fraud looked indistinguishable from clean at the feature "
            "level, OR the fraudster used a brand-new identity/device/card with no "
            "history so velocity/graph signals were low. Check the event's "
            "fraud_vector and the per-model scores in the investigation report."
        ),
        "remedy": (
            "1) Confirm the payment truly leaked (a chargeback/webhook) and feed it "
            "back: in the dashboard click 'Mark fraud' on that transaction, or via "
            "POST /api/feedback/{event_id}/correct (is_fraud=true). 2) The online "
            "correction layer will immediately bias future similar scores upward; "
            "run 'Trigger retrain' to fold it into the models. 3) Review whether a "
            "new fraud vector (e.g. a new scam pattern) is undetected and add "
            "features/rules for it. 4) Lower the review threshold so borderline "
            "cases go to phone verification instead of approve."
        ),
    },
    {
        "id": "card_testing",
        "title": "Card-testing / carding burst",
        "severity": "high",
        "tags": ["card testing", "carding", "card test", "micro", "tiny amount",
                 "burst", "velocity", "checker", "enumeration"],
        "questions": [
            "card testing burst carding small charges",
            "many tiny charges same card",
            "card number enumeration checking",
            "high velocity small amount fraud",
        ],
        "description": "Automated small-value charges used to check stolen cards",
        "diagnosis": (
            "Signals: many micro payments (<= Rs 15) on one card/device within a "
            "short window, round amounts, fast typing cadence, high count_card_60m "
            "velocity. The card_test_flag and velocity_flag features fire; graph "
            "engine shows the card/device at the centre of a shared cluster."
        ),
        "remedy": (
            "The detector auto-blocks and the card-test vector is labelled in the "
            "dashboard. For extra safety: 1) add a velocity cap on a single card "
            "(e.g. block > N attempts/hour). 2) Require 3DS on new devices. "
            "3) Blacklist the card_last4/device once confirmed. 4) Run the 'Card-"
            "testing burst' demo to verify the model still flags it after any "
            "retrain."
        ),
    },
    {
        "id": "account_takeover",
        "title": "Account takeover (ATO) / new device login",
        "severity": "high",
        "tags": ["account takeover", "ato", "account", "hijack", "new device",
                 "credential", "login", "stolen account"],
        "questions": [
            "account takeover hijacked account new device",
            "stolen account making payments",
            "new device on existing account suspicious",
            "credential stuffing",
        ],
        "description": "A fraudster uses a victim's saved account",
        "diagnosis": (
            "Behaviour AI flags the deviation from the account's established "
            "profile: novel device (is_new_device), different typing cadence, "
            "changed method mix, and an elevated recent_failure_rate. Graph "
            "engine links the new device to the account node."
        ),
        "remedy": (
            "1) Gate the first payment from a new device on an existing account "
            "via the phone-verification flow (review band) before settlement. "
            "2) If confirmed, mark the transaction fraud so the model learns. "
            "3) Recommend the merchant force a password/3DS on device change. "
            "4) Monitor failed-payment rate per account as an ATO tell."
        ),
    },
    {
        "id": "behaviour_anomaly_review",
        "title": "Behaviour-anomaly escalation to review (legit novelty)",
        "severity": "medium",
        "tags": ["behaviour", "anomaly", "review band", "novel", "escalation",
                 "p_behav", "autoencoder"],
        "questions": [
            "why is this being sent to review band behaviour",
            "behaviour anomaly escalation legitimate novelty",
            "high reconstruction error behaviour autoencoder",
            "new customer reviewed",
        ],
        "description": "Novel-but-legitimate behaviour gets routed to phone verification",
        "diagnosis": (
            "Any payment with behaviour anomaly p_behaviour >= 0.9 AND amount >= "
            "Rs 1000 is auto-escalated to review even if overall risk is low. This "
            "is by design (defense-only) to catch disguised attacks, but brand-new "
            "legit customers with no history will also trigger it because they have "
            "no behavioural baseline."
        ),
        "remedy": (
            "This is expected. The payment is held for a phone-call OTP and settles "
            "once the payer confirms ownership (see the 'Phone-call payment "
            "confirmation' panel). To reduce noise: 1) ensure legit customers are "
            "enrolled/baselined before high-value first purchases. 2) Keep the "
            "guard but only for high value (raise behaviour_review_min_amount). "
            "3) Do NOT auto-approve — verification is the correct safe action."
        ),
    },
    {
        "id": "review_backlog",
        "title": "Review-band backlog (pending phone verifications)",
        "severity": "medium",
        "tags": ["review backlog", "pending", "verification", "otp", "call",
                 "stuck", "queue", "unresolved"],
        "questions": [
            "many pending phone verifications backlog",
            "reviews stuck unresolved queue",
            "otp verification not resolving",
            "slow settlement review band",
        ],
        "description": "Too many payments stuck in the medium-risk review band",
        "diagnosis": (
            "Check GET /api/verification for sessions stuck in 'pending' status; "
            "the OTP TTL is 300s and max 3 attempts before auto-block. A build-up "
            "means not enough operators are completing the confirm/deny flow, or "
            "the phone numbers are unreachable."
        ),
        "remedy": (
            "1) Keep an operator on the 'Phone-call payment confirmations' panel and "
            "complete each call (Confirm OTP / Resend / Deny) promptly — expired "
            "sessions auto-block. 2) If calls can't connect, check the Twilio mode "
            "(simulated vs real); trial Twilio blocks outbound calls until the "
            "account is upgraded to billing. 3) Confirm/deny also feed the continual "
            "learning loop, so resolving them improves the model too."
        ),
    },
    {
        "id": "model_retrain",
        "title": "Retraining the model (continual learning)",
        "severity": "low",
        "tags": ["retrain", "retraining", "train", "learning", "feedback", "update",
                 "continual", "new data"],
        "questions": [
            "how do i retrain the model",
            "retrain on new feedback data",
            "update the model with corrections",
            "continual learning retrain button",
        ],
        "description": "Fold confirmed feedback back into the supervised models",
        "diagnosis": (
            "Every scored transaction is recorded and can be labelled by phone-"
            "verification verdicts (confirm=clean, deny=fraud) or manual 'Mark "
            "clean/fraud'. These accumulate in backend/data/feedback.json. The "
            "online correction layer adapts immediately; a full retrain bakes the "
            "labels into the ML-risk + Investigator models."
        ),
        "remedy": (
            "1) Click 'Trigger retrain' in the 'Continual learning' dashboard card "
            "(or POST /api/learning/retrain). 2) It rebuilds on the original "
            "synthetic data PLUS confirmed feedback, then hot-swaps the live model. "
            "3) Verify held-out metrics via /api/test-metrics after retraining to "
            "ensure precision/recall did not regress. 4) Confirm-feedback rows from "
            "review-band users are always learnable by design."
        ),
    },
    {
        "id": "twilio_real_calls",
        "title": "Real Twilio calls blocked / not connecting",
        "severity": "medium",
        "tags": ["twilio", "call", "phone", "sms", "real mode", "simulated",
                 "trial", "billing", "audio recording"],
        "questions": [
            "real twilio calls not connecting blocked",
            "trial account can't call upgrade billing",
            "switch from simulated to real phone mode",
            "call audio recording not working",
        ],
        "description": "Outbound verification calls fail or stay simulated",
        "diagnosis": (
            "The backend runs in 'real' Twilio mode only when the twilio package is "
            "installed AND TWILIO_ACCOUNT_SID/AUTH_TOKEN/PHONE_NUMBER are set in "
            "backend/.env. Trial accounts return HTTP 400 ('trial accounts have "
            "limited parameter access') and cannot place outbound calls until "
            "billing is added, so the system falls back to simulated."
        ),
        "remedy": (
            "1) Upgrade the Twilio account: Console -> Billing -> add a payment "
            "method (a small credit is needed) to unlock outbound calls and audio "
            "recording (record=True is already wired). 2) Verify backend/.env has "
            "the three TWILIO_* values and restart; GET /api/verification reports "
            "mode. 3) Rotate the Auth Token after demo use. 4) Until then the demo "
            "uses the simulated OTP + call script, which works fully offline."
        ),
    },
    {
        "id": "razorpay_keys",
        "title": "Razorpay live vs test keys / webhooks",
        "severity": "medium",
        "tags": ["razorpay", "keys", "webhook", "order", "rzp", "test key",
                 "live key", "payment.captured"],
        "questions": [
            "razorpay keys not working live vs test",
            "webhook payment captured not ingested",
            "create test order razorpay",
            "real payment integration",
        ],
        "description": "Optional real Razorpay test-mode integration",
        "diagnosis": (
            "Real integration is optional. Set RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET "
            "(rzp_test_ only) in backend/.env to create orders and ingest "
            "payment.captured/order.paid webhooks. Never commit .env and never use "
            "rzp_live_ keys in a demo. GET /api/rzp/status shows configuration."
        ),
        "remedy": (
            "1) Use test keys only. 2) Create an order via POST /api/rzp/create-order. "
            "3) Send captured webhooks to POST /api/rzp/webhook — each runs through "
            "the full pipeline and returns scores + evidence. 4) Rotate keys if they "
            "leak. The system works fully in keyless mode without them."
        ),
    },
    {
        "id": "support_scam_fraud",
        "title": "Support-scam / social-engineering fraud",
        "severity": "high",
        "tags": ["support scam", "social engineering", "scam", "phishing",
                 "refund scam", "deepfake", "social"],
        "questions": [
            "support scam social engineering refund scam",
            "fraudster convincing victim to approve",
            "deepfake voice scam phone",
            "authorized push payment fraud",
        ],
        "description": "Scammers convince the payer to authorize a fraudulent payment",
        "diagnosis": (
            "The payer knowingly approves but under deception, so OTP confirm may "
            "pass. Signals are behaviour-based: rush, high value, unusual merchant, "
            "new device. The phone-call script deliberately NEVER asks the payer to "
            "read a code back in a phishable way — it sends the OTP and asks them to "
            "confirm it, and asks 'was this payment made by you?', reducing "
            "social-engineering pressure."
        ),
        "remedy": (
            "1) In the call script, an agent who detects hesitation/coercion should "
            "Deny (escalate to block) rather than confirm. 2) Use velocity + "
            "high-value guards to push such payments into review. 3) Educate payers "
            "that Razorpay never asks them to send money to 'reverse' a refund. "
            "4) Mark confirmed cases fraud so the model learns the behavioural "
            "signature."
        ),
    },
    {
        "id": "decision_thresholds",
        "title": "How decisions & thresholds work",
        "severity": "low",
        "tags": ["threshold", "decision", "approve", "review", "block", "0.44",
                 "0.80", "probability", "how decisions"],
        "questions": [
            "how are decisions made approve review block",
            "what do thresholds 0.44 0.80 mean",
            "why review not block medium risk",
            "explain the decision logic",
        ],
        "description": "The AI Investigator decision rule",
        "diagnosis": _DECISION_CAVEAT,
        "remedy": _DECISION_CAVEAT,
    },
    {
        "id": "verify_event_api",
        "title": "Verify a single payment / force phone verification",
        "severity": "low",
        "tags": ["verify", "investigate", "score", "api", "single payment",
                 "demo", "borderline"],
        "questions": [
            "how to score a single payment verify",
            "run a live fraud check investigate",
            "demo borderline review scenario",
            "force a phone verification test",
        ],
        "description": "Manually test or verify one payment",
        "diagnosis": (
            "Use the dashboard 'Live fraud check' (scenarios: fraud burst, "
            "borderline phone-verify, clean) or POST /api/investigate with an event. "
            "A borderline payment lands in review and returns a phone_verification "
            "handle ready for OTP confirmation."
        ),
        "remedy": (
            "POST /api/investigate with {event:{...}, history:[...]}. To force the "
            "phone flow, use the 'Borderline — phone verify' scenario. Complete it "
            "via the verification panel or the returned handle."
        ),
    },
    {
        "id": "metrics_meaning",
        "title": "Reading the honest metrics (false-positive cost)",
        "severity": "low",
        "tags": ["metrics", "precision", "recall", "f1", "cost", "auc", "false",
                 "negative cost", "money prevented", "test metrics"],
        "questions": [
            "what do the test metrics precision recall mean",
            "false positive cost false negative cost",
            "how much money prevented",
            "auc investigator meaning",
        ],
        "description": "Interpreting the held-out test metrics",
        "diagnosis": (
            "Held-out test (seed 42): Precision 1.000 (0 false positives), Recall "
            "0.973 (180/185 fraud blocked), F1 0.986, Investigator AUC 0.998. Cost: "
            "false-positive cost Rs 0.00, false-negative cost Rs 8,466.14, total "
            "Rs 8,466.14 vs a no-intervention baseline of Rs 313,247.14, i.e. about "
            "Rs 304,781 in fraud prevented. The 5 unreal 'misses' were review-band "
            "and would be caught by phone verification, not released."
        ),
        "remedy": (
            "These are read live from GET /api/test-metrics. A rising false-positive "
            "cost means legit customers are being blocked — see the 'false-positive "
            "surge' guidance. A rising false-negative cost means fraud is leaking — "
            "label those events and retrain (see 'false negatives' and 'retrain')."
        ),
    },
]


def build_corpus() -> list[dict]:
    """Flatten KNOWLEDGE into retrieval chunks. Each question phrase becomes its
    own searchable chunk pointing back to the entry, so TF-IDF matching against a
    user's natural-language question is strong."""
    chunks = []
    for entry in KNOWLEDGE:
        for q in entry["questions"]:
            chunks.append({
                "type": "question",
                "entry_id": entry["id"],
                "text": q,
            })
    return chunks
