"""
Low-level diagnostic: call encryption_key, getsessiondata (get_session_id), invalid_sess, createSession
and append redacted JSON responses to alice_support_log.txt
"""
import sys, json, time
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

from datetime import datetime
from dotenv import load_dotenv
import os
import traceback

load_dotenv()

USER_ID = os.getenv('ALICEBLUE_USER_ID')
API_KEY = os.getenv('ALICEBLUE_API_KEY')
TOTP = os.getenv('ALICEBLUE_TOTP_SECRET')

from pya3 import Aliceblue
import pyotp

out = {
    'timestamp': datetime.utcnow().isoformat() + 'Z',
    'env_ok': bool(USER_ID and API_KEY and TOTP),
    'calls': {}
}

try:
    alice = Aliceblue(user_id=USER_ID, api_key=API_KEY)
    out['client_type'] = str(type(alice))

    # 1) encryption_key
    try:
        data = {'userId': USER_ID.upper()}
        enc = alice._post('encryption_key', data)
        out['calls']['encryption_key'] = enc
    except Exception as e:
        out['calls']['encryption_key_error'] = repr(e)
        out['calls']['encryption_key_trace'] = traceback.format_exc()

    # 2) get_session_id with OTP
    try:
        otp = pyotp.TOTP(TOTP).now()
        out['generated_otp'] = otp
        gs = alice.get_session_id(otp)
        out['calls']['get_session_id_with_otp'] = gs
    except Exception as e:
        out['calls']['get_session_id_with_otp_error'] = repr(e)
        out['calls']['get_session_id_with_otp_trace'] = traceback.format_exc()

    # 3) get_session_id without OTP (to compare previous behavior)
    try:
        gs2 = alice.get_session_id()
        out['calls']['get_session_id_no_otp'] = gs2
    except Exception as e:
        out['calls']['get_session_id_no_otp_error'] = repr(e)
        out['calls']['get_session_id_no_otp_trace'] = traceback.format_exc()

    # 4) invalid_sess
    try:
        sess = getattr(alice, 'session_id', None)
        out['observed_session_id'] = sess
        invalid = alice.invalid_sess(sess)
        out['calls']['invalid_sess'] = invalid
    except Exception as e:
        out['calls']['invalid_sess_error'] = repr(e)
        out['calls']['invalid_sess_trace'] = traceback.format_exc()

    # 5) createSession (may error if session None)
    try:
        create = alice.createSession(sess)
        out['calls']['createSession'] = create
    except Exception as e:
        out['calls']['createSession_error'] = repr(e)
        out['calls']['createSession_trace'] = traceback.format_exc()

    # Additional: base urls
    try:
        out['client_urls'] = {
            'base_url': getattr(alice, 'base_url', None),
            '_sub_urls': getattr(alice, '_sub_urls', None),
            'websocket_url': getattr(alice, 'websocket_url', None)
        }
    except Exception:
        pass

except Exception as e:
    out['client_init_error'] = repr(e)
    out['client_init_trace'] = traceback.format_exc()

# Redact sensitive fields
redacted = json.dumps(out, indent=2)
redacted = redacted.replace(USER_ID or '', USER_ID[:5] + '***' if USER_ID else USER_ID)
if API_KEY:
    redacted = redacted.replace(API_KEY, API_KEY[:5] + '***')
if TOTP:
    redacted = redacted.replace(TOTP, TOTP[:5] + '***')

# Append to support log
log_path = 'alice_support_log.txt'
with open(log_path, 'a', encoding='utf-8') as f:
    f.write('\n' + '='*60 + '\n')
    f.write('LOW-LEVEL TRACE - ' + datetime.utcnow().isoformat() + 'Z\n')
    f.write(redacted)
    f.write('\n' + '='*60 + '\n')

print('Low-level trace appended to', log_path)
print(redacted)
