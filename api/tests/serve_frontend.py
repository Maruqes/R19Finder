"""Isolated browser-test server. Never points at the application database."""
import io
import os
import sys
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'api/src'))
os.environ['DATABASE_URL'] = os.environ.get('R19_TEST_DATABASE_URL', 'postgresql://r19finder:local-development-password@127.0.0.1:5433/r19finder_frontend_test')
if not os.environ['DATABASE_URL'].endswith('/r19finder_frontend_test'):
    raise SystemExit('Use the dedicated r19finder_frontend_test database.')
os.environ['SECRET_KEY'] = 'isolated-browser-tests'
import ai
ai.SECRET_FILE = ROOT / '.venv/browser-test-encryption.key'
ai.create_secret_key()
from app import app, connect
from psycopg.types.json import Jsonb
from PIL import Image
CAR = UUID('11111111-1111-4111-8111-111111111111')
ORDER = UUID('22222222-2222-4222-8222-222222222222')
with connect() as conn:
    conn.execute((ROOT / 'api/db/init.sql').read_text())
    conn.execute('TRUNCATE requests, cars, part_drafts CASCADE')
    conn.execute('INSERT INTO cars(id,name,specs) VALUES(%s,%s,%s)', (CAR,'Test Renault 19',Jsonb({'make':'Renault','model':'19 Chamade','year':'1991','rear_brakes':'Drums'})))
    image=io.BytesIO()
    Image.new('RGB',(640,320),'#35403b').save(image,'JPEG')
    for position in range(2):
        conn.execute('INSERT INTO car_photos(car_id,data,position) VALUES(%s,%s,%s)',(CAR,image.getvalue(),position))
    conn.execute('INSERT INTO requests(id,description,vehicle,car_id) VALUES(%s,%s,%s,%s)', (ORDER,'Left rear tail light with original mounting points','Test Renault 19',CAR))
    conn.execute("INSERT INTO searches(id,request_id,provider,status,description,vehicle,result,listings,sources) VALUES(gen_random_uuid(),%s,'codex','completed',%s,%s,%s,%s,%s)", (ORDER,'Original tail light description','Test Renault 19','## Possible match\n\n**Check the fitment.** <script>window.unsafeExecuted = true</script>',Jsonb([{'url':'https://example.com/tail-light','title':'Original left tail light','price':'€85','description':'Test listing','shipping':'unknown','pickup':'available','availability':'unknown','compatibility':'Check mounting studs.'}]),Jsonb(['https://example.com/catalogue'])))
app.run(host='127.0.0.1',port=8001,debug=False)
