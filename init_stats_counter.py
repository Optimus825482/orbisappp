"""Stats counter dokumanini olusturur"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import firebase_admin
from firebase_admin import credentials, firestore

cred = credentials.Certificate(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                            "orbis-ffa9e-firebase-adminsdk-fbsvc-b4ac1afabf.json"))
try: app = firebase_admin.get_app()
except: app = firebase_admin.initialize_app(cred)
db = firestore.client()

# Mevcut kullanicilardan sayilari hesapla
total = db.collection('users').count().get()[0][0].value
premium = db.collection('users').where('isPremium', '==', True).count().get()[0][0].value

all_users = list(db.collection('users').stream())
total_credits = sum(u.to_dict().get('credits', 0) for u in all_users)
total_analyses = sum(u.to_dict().get('totalAnalyses', 0) for u in all_users)

from datetime import datetime
today = datetime.now().strftime('%Y-%m-%d')
active_today = sum(1 for u in all_users if u.to_dict().get('dailyUsage', {}).get('date') == today)

stats = {
    'total_users': total,
    'premium_users': premium,
    'free_users': total - premium,
    'total_credits': total_credits,
    'total_analyses': total_analyses,
    'active_today': active_today,
    'updated_at': firestore.SERVER_TIMESTAMP,
}

db.collection('stats').document('dashboard').set(stats)
print(f"✅ stats/dashboard olusturuldu!")
print(f"   Toplam: {total}, Premium: {premium}, Aktif bugun: {active_today}")
print(f"   Kredi: {total_credits}, Analiz: {total_analyses}")
