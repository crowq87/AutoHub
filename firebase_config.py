import firebase_admin
from firebase_admin import credentials

cred = credentials.Certificate(
    "firebase/autohub-3b-firebase-adminsdk-fbsvc-90bf829b9c.json"
)

firebase_admin.initialize_app(cred)