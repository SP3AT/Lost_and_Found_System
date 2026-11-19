# Lost & Found

A simple Flask and SQLite lost-and-found application. Users register, report lost or found items, and submit ownership claims for found items. Administrators see all reports and claims, approve or reject claims, and mark approved items as returned. There is no AI or automatic matching.

## Setup

From this directory, install Python 3.9+ and Flask:

```bash
pip install -r requirements.txt
```

Set a long, random `SECRET_KEY` environment variable so login sessions remain valid across restarts. Set `DATABASE_PATH` if you want a database somewhere other than `lost_found.db` in the current directory. Existing item records are retained and migrated automatically; older records do not have an account owner.

Create an administrator (you will be prompted for a password):

```bash
flask --app flask_app create-admin admin
```

Run the application:

```bash
python flask_app.py
```

Open http://127.0.0.1:5000. Regular users can register on the login page; choose User or Administrator on the login page to match the account you are using. Administrators use an account created by the command above, not public registration. Search reports by keyword, type, or status from the dashboard. Report contact information is visible to administrators, not other users. Claims are reviewed manually; approving one rejects other pending claims for that item.

Reports can include an optional JPEG, PNG, or WebP photo (request limit 5 MB), visible to signed-in users. The dashboard separates lost reports, found reports, returned items, and claims into sections. Lost reports are not automatically matched or closed when a found item is returned.

The built-in server is intended for local use. For a public deployment, use a production WSGI server, HTTPS, a persistent secret key, and appropriate operational security measures.
