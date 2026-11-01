"""
Create a user from the command line. This is how the first administrator is made.

    python -m backend.create_admin --username yourname --email you@example.com --full-name "Your Name"

The password is typed at a prompt (it is not shown) and is stored only as a hash.
It uses DATABASE_URL from .env, which is your real database.
"""

import argparse
import getpass
import sys

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from backend.database import get_session_factory
from backend.services import users as user_service


def main(argv=None):
    p = argparse.ArgumentParser(description="Create a GeoFlood AI user")
    p.add_argument("--username", required=True)
    p.add_argument("--email", required=True)
    p.add_argument("--full-name", default=None)
    p.add_argument("--role", choices=user_service.ROLES, default="admin")
    args = p.parse_args(argv)

    password = getpass.getpass("Password: ")
    if password != getpass.getpass("Repeat password: "):
        sys.exit("The two passwords do not match. Nothing was created.")

    db = get_session_factory()()
    try:
        user = user_service.create_user(db, username=args.username, email=args.email, password=password,
                                        role=args.role, full_name=args.full_name)
        db.commit()
    except ValueError as err:
        db.rollback()
        sys.exit(f"Not created: {err}")
    except IntegrityError:
        db.rollback()
        sys.exit("Not created: that username or email already exists.")
    except SQLAlchemyError:
        db.rollback()
        sys.exit("Not created: the database is unavailable. Check DATABASE_URL and that PostgreSQL is running.")
    finally:
        db.close()

    print(f"Created {user['role']} '{user['username']}' (user id {user['user_id']}).")


if __name__ == "__main__":
    main()
