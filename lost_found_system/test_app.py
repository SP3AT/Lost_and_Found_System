import os
import tempfile
import unittest
from io import BytesIO
from PIL import Image

temp_dir = tempfile.TemporaryDirectory()
os.environ['DATABASE_PATH'] = os.path.join(temp_dir.name, 'test.db')
from flask_app import app, db
from werkzeug.security import generate_password_hash


class WorkflowTest(unittest.TestCase):
    def setUp(self):
        with db.get_connection() as conn:
            conn.execute('DELETE FROM claims')
            conn.execute('DELETE FROM items')
            conn.execute('DELETE FROM users')
            conn.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, 'admin')",
                         ('admin', generate_password_hash('password123')))
        self.client = app.test_client()

    def post(self, path, data):
        with self.client.session_transaction() as session:
            session['csrf_token'] = 'test-token'
        return self.client.post(path, data={**data, 'csrf_token': 'test-token'})

    def login(self, username):
        return self.post('/login', {'username': username, 'password': 'password123', 'role': 'admin' if username == 'admin' else 'user'})

    def test_claim_review(self):
        self.post('/register', {'username': 'finder', 'password': 'password123'})
        self.post('/register', {'username': 'owner', 'password': 'password123'})
        self.login('finder')
        self.post('/report', {'title': 'Keys', 'category': 'Keys', 'item_type': 'found',
                             'description': 'A keyring', 'location': 'Library',
                             'date_reported': '2026-11-17', 'reporter_contact': 'private'})
        with db.get_connection() as conn:
            item_id = conn.execute('SELECT id FROM items').fetchone()['id']
        self.post('/logout', {})
        self.login('owner')
        self.assertNotIn(b'private', self.client.get('/dashboard?tab=found').data)
        self.assertEqual(self.post(f'/items/{item_id}/claim', {'details': 'Blue keyring'}).status_code, 302)
        with db.get_connection() as conn:
            claim_id = conn.execute('SELECT id FROM claims').fetchone()['id']
        self.assertEqual(self.post(f'/claims/{claim_id}/review', {'decision': 'Approved'}).status_code, 403)
        self.post('/logout', {})
        self.login('admin')
        self.assertIn(b'private', self.client.get('/dashboard?tab=found').data)
        self.assertEqual(self.post(f'/claims/{claim_id}/review', {'decision': 'Approved'}).status_code, 302)
        self.assertEqual(self.post(f'/items/{item_id}/returned', {}).status_code, 302)
        with db.get_connection() as conn:
            self.assertEqual(conn.execute('SELECT status FROM items WHERE id = ?', (item_id,)).fetchone()['status'], 'Returned')
            self.assertEqual(conn.execute('SELECT status FROM claims WHERE id = ?', (claim_id,)).fetchone()['status'], 'Approved')

    def test_csrf_required(self):
        self.assertEqual(self.client.post('/login', data={}).status_code, 400)

    def test_photo_and_tabs(self):
        self.post('/register', {'username': 'owner', 'password': 'password123'})
        self.login('owner')
        image = BytesIO()
        Image.new('RGB', (2, 2), 'red').save(image, format='PNG')
        image.seek(0)
        fields = {'title': 'Red bag', 'category': 'Bag', 'item_type': 'lost',
                  'description': 'Small bag', 'location': 'Park',
                  'date_reported': '2026-11-17', 'reporter_contact': 'private'}
        self.assertEqual(self.post('/report', {**fields, 'photo': (image, 'bag.png')}).status_code, 302)
        with db.get_connection() as conn:
            item_id = conn.execute('SELECT id FROM items').fetchone()['id']
        self.assertIn(b'Red bag', self.client.get('/dashboard?tab=lost').data)
        self.assertNotIn(b'Red bag', self.client.get('/dashboard?tab=found').data)
        self.assertEqual(self.client.get(f'/items/{item_id}/photo').mimetype, 'image/png')
        with db.get_connection() as conn:
            conn.execute("UPDATE items SET status = 'Returned' WHERE id = ?", (item_id,))
        self.assertNotIn(b'Red bag', self.client.get('/dashboard?tab=lost').data)
        self.assertIn(b'Red bag', self.client.get('/dashboard?tab=returned').data)
        self.assertEqual(self.post('/report', {**fields, 'photo': (BytesIO(b'not an image'), 'bad.png')}).status_code, 400)
        self.post('/logout', {})
        self.assertEqual(self.client.get(f'/items/{item_id}/photo').status_code, 302)


if __name__ == '__main__':
    unittest.main()
