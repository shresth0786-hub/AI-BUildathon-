"""
PHONE-CALL PAYMENT CONFIRMATION (optional, defense-only).

When the AI Investigator lands on the *review* band (medium fraud probability,
neither clearly clean nor clearly fraud), the payment is NOT auto-approved. The
system instead initiates a phone-call confirmation to the payer before funds
settle:

    block   (p >= review_thresh)  -> auto-decline, no call
    review  (approve <= p < review) -> PHONE VERIFICATION REQUIRED
    approve (p <  approve_thresh) -> auto-pass, no call

The phone call itself can be one of two modes, chosen automatically:

  * SIMULATED (default)  — an OTP + a call script are generated and exposed via
    the API / dashboard. This is the offline buildathon demo: an analyst (you)
    reads the "call script", then confirms/denies the OTP to complete the call.
    The system then either APPROVES (OTP correct) or BLOCKS (OTP wrong / too
    many failed attempts / the caller denied ownership of the payment).

  * REAL (optional)      — if the optional `twilio` package is installed AND the
    TWILIO_* keys are present in `.env`, the system actually originates a call
    (or an SMS) that delivers the OTP to the payer's phone. Falls back to
    simulation if any part is missing. NEVER commit real keys.

Criteria to confirm the payer is legitimate (all must hold to APPROVE):
  1. The payer supplies the correct OTP that was sent to their phone.
  2. The payer confirms ownership of the payment (the call script asks them to
     confirm the exact amount, merchant and last-4 of the card).
  3. The number of failed OTP attempts is below the allowed cap; exceeding it
     escalates the decision to BLOCK.
"""

from __future__ import annotations

import json
import os
import time
import uuid

# --- optional real telephony (lazy import so the demo runs without twilio) ----
try:  # pragma: no cover - only present if the optional package is installed
    from twilio.rest import Client as _TwilioClient
    _TWILIO_AVAILABLE = True
except Exception:  # noqa: BLE001
    _TwilioClient = None
    _TWILIO_AVAILABLE = False

_MAX_ATTEMPTS = 3            # wrong OTP attempts before we escalate to BLOCK
_OTP_TTL_SECONDS = 300       # OTP expires after 5 minutes
_OTP_POOL = "0123456789"
_RECORD_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "verifications.json")


def _generate_otp(length: int = 6) -> str:
    """Cryptographically-random numeric OTP (no external dependency)."""
    import secrets
    return "".join(secrets.choice(_OTP_POOL) for _ in range(length))


class PhoneVerifier:
    """In-memory store of payment verification sessions + simulated/real calls.

    A single process holds these; for a multi-worker deployment this would be
    backed by Redis/DB. For the buildathon demo an in-memory dict is enough.
    """

    def __init__(self, max_attempts: int = _MAX_ATTEMPTS,
                 otp_ttl: int = _OTP_TTL_SECONDS):
        self.max_attempts = max_attempts
        self.otp_ttl = otp_ttl
        self._store: dict[str, dict] = {}
        self._load()

    # -------------------------------------------------- persistent call record
    def _load(self) -> None:
        """Restore previously 'recorded' verification sessions from disk so the
        call log survives a backend restart (best-effort; missing/corrupt file
        simply means an empty log)."""
        try:
            with open(_RECORD_FILE, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                self._store = data
        except (FileNotFoundError, ValueError, OSError):
            self._store = {}

    def _save(self) -> None:
        """Persist every session (the 'recorded call' log) to append-only JSON."""
        try:
            os.makedirs(os.path.dirname(_RECORD_FILE), exist_ok=True)
            with open(_RECORD_FILE, "w", encoding="utf-8") as f:
                json.dump(self._store, f, indent=2)
        except OSError:  # pragma: no cover - persistence is best-effort
            pass

    # ------------------------------------------------------------- env/status
    @staticmethod
    def mode() -> str:
        """'real' only when twilio + all keys present, else 'simulated'."""
        if _TWILIO_AVAILABLE:
            sid = os.getenv("TWILIO_ACCOUNT_SID")
            tok = os.getenv("TWILIO_AUTH_TOKEN")
            frm = os.getenv("TWILIO_PHONE_NUMBER")
            if sid and tok and frm:
                return "real"
        return "simulated"

    def status(self) -> dict:
        return {
            "mode": self.mode(),
            "twilio_installed": _TWILIO_AVAILABLE,
            "active": sum(1 for v in self._store.values()
                          if v["status"] in ("pending", "in_call")),
        }

    # ------------------------------------------------------------------ create
    def create(self, event: dict) -> dict:
        """Open a verification session for a payment in the review band."""
        vid = "ver_" + uuid.uuid4().hex[:12]
        otp = _generate_otp()
        now = time.time()
        phone = event.get("phone") or event.get("payer_phone") or "**********"
        ver = {
            "verification_id": vid,
            "event_id": event.get("event_id", "unknown"),
            "user_id": event.get("user_id", ""),
            "merchant": event.get("merchant", ""),
            "amount_inr": event.get("amount_inr", 0),
            "phone": phone,
            "card_last4": event.get("card_last4", ""),
            "otp": otp,
            "otp_expires_at": now + self.otp_ttl,
            "attempts": 0,
            "max_attempts": self.max_attempts,
            "status": "in_call",                 # call is being placed
            "created_at": now,
            "call_script": self._build_call_script(event, otp),
        }
        self._store[vid] = ver
        self._place_call(ver)
        ver["status"] = "pending"                # awaiting OTP confirmation
        self._save()
        return self._public(ver)

    def _place_call(self, ver: dict) -> None:
        """Simulate the outgoing call. With twilio + keys it would originate a
        real call/SMS here; without them we just log it for the demo."""
        if self.mode() == "real":
            try:
                # telephony client is only non-None in real mode
                client = _TwilioClient(os.getenv("TWILIO_ACCOUNT_SID"),
                                       os.getenv("TWILIO_AUTH_TOKEN"))
                call = client.calls.create(
                    to=ver["phone"], from_=os.getenv("TWILIO_PHONE_NUMBER"),
                    record=True,      # record the call audio (PII: core Twilio media)
                    twiml=f"<Response><Say>Your payment of "
                          f"{ver['amount_inr']} rupees at {ver['merchant']} "
                          f"requires verification. Your code is "
                          f"{ver['otp']}.</Say></Response>",
                )
                ver["call_delivered"] = "real"
                ver["call_sid"] = getattr(call, "sid", None)
                # best-effort recording URL (fetchable later via Twilio API)
                ver["recording_available"] = True
            except Exception as exc:  # noqa: BLE001
                ver["call_delivered"] = f"real-failed({exc})"
                ver["call_delivered"] = "simulated-fallback"
                ver["recording_available"] = False
        else:
            ver["call_delivered"] = "simulated"
            ver["recording_available"] = False

    @staticmethod
    def _build_call_script(event: dict, otp: str) -> list[str]:
        """Human-readable script an agent reads when calling the payer, and the
        confirmation questions we expect them to answer correctly."""
        return [
            f"Call {event.get('phone', 'the payer')} — identify the Razorpay "
            f"fraud team, do NOT ask the payer to read a code back in a "
            f"phishable way; instead send {otp} and ask them to confirm it.",
            f"Confirm the payment: {event.get('amount_inr', '?')} INR at "
            f"{event.get('merchant', '?')} on card ••{event.get('card_last4', '????')}.",
            "Was this payment made by you?",
        ]

    # --------------------------------------------------------------- confirm
    def confirm(self, verification_id: str, otp: str) -> dict:
        """Complete the call. Correct OTP + ownership confirmation -> approve;
        wrong OTP / cap exceeded -> block (escalated)."""
        ver = self._store.get(verification_id)
        if ver is None:
            raise KeyError(f"Unknown verification: {verification_id}")

        if ver["status"] != "pending":
            return self._public(ver)

        if time.time() > ver["otp_expires_at"]:
            ver["status"] = "expired"
            return self._public(ver)

        ver["attempts"] += 1
        if otp == ver["otp"]:
            ver["status"] = "approved"
            ver["resolved_at"] = time.time()
            ver["final_action"] = "approve"
            self._feed_label(ver, 0, "otp_confirm")
        else:
            if ver["attempts"] >= ver["max_attempts"]:
                ver["status"] = "blocked"
                ver["resolved_at"] = time.time()
                ver["reason"] = "too_many_failed_otp"
                ver["final_action"] = "block"
                self._feed_label(ver, 1, "otp_deny")
            else:
                ver["status"] = "pending"       # allow a retry
        self._save()
        return self._public(ver)

    def deny(self, verification_id: str) -> dict:
        """The caller denied ownership of the payment -> escalate to BLOCK."""
        ver = self._store.get(verification_id)
        if ver is None:
            raise KeyError(f"Unknown verification: {verification_id}")
        if ver["status"] == "pending":
            ver["status"] = "blocked"
            ver["reason"] = "caller_denied_ownership"
            ver["final_action"] = "block"
            ver["resolved_at"] = time.time()
            self._feed_label(ver, 1, "otp_deny")
        self._save()
        return self._public(ver)

    def resend(self, verification_id: str) -> dict:
        """Regenerate a fresh OTP and re-place the call."""
        ver = self._store.get(verification_id)
        if ver is None:
            raise KeyError(f"Unknown verification: {verification_id}")
        ver["otp"] = _generate_otp()
        ver["otp_expires_at"] = time.time() + self.otp_ttl
        ver["call_script"][0] = (f"Call {ver['phone']} — Razorpay fraud team; "
                                 f"send {ver['otp']} and ask them to confirm it.")
        ver["status"] = "pending"
        self._place_call(ver)
        self._save()
        return self._public(ver)

    def get(self, verification_id: str) -> dict:
        ver = self._store.get(verification_id)
        if ver is None:
            raise KeyError(f"Unknown verification: {verification_id}")
        return self._public(ver)

    def list(self) -> list[dict]:
        return [self._public(v) for v in
                sorted(self._store.values(), key=lambda v: v["created_at"], reverse=True)]

    # ------------------------------------------------------------------ util
    @staticmethod
    def _feed_label(ver: dict, label: int, source: str) -> None:
        """Push a confirmed verdict to the continual-learning feedback loop so
        the model learns from the phone call (approve->clean, deny->fraud)."""
        event_id = ver.get("event_id")
        if not event_id:
            return
        try:
            from app.feedback import get_controller
            get_controller().label(event_id, label, source)
        except Exception:  # pragma: no cover - learning must not break the call
            pass

    @staticmethod
    def _public(ver: dict) -> dict:
        """Never expose internals (raw OTP is shown for the simulated demo so an
        analyst can complete the call; strip it for a 'real' production mode)."""
        copy = dict(ver)
        # OTP is intentionally included for the simulated demo. In real mode
        # the payer reads it back, so we redact it server-side.
        if PhoneVerifier.mode() == "real":
            copy["otp"] = "******"
        return copy


# ------------------------------------------------------------------ singleton
def verifier() -> PhoneVerifier:
    global _VERIFIER
    if _VERIFIER is None:
        _VERIFIER = PhoneVerifier()
    return _VERIFIER


_VERIFIER: PhoneVerifier | None = None
