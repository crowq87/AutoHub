import json
import os
import firebase_admin
from firebase_admin import credentials

firebase_config = json.loads(os.environ["FIREBASE_CREDENTIALS"])
cred = credentials.Certificate(firebase_config)

firebase_admin.initialize_app(cred)