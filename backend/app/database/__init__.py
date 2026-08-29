# Database package (app.database)
#
# Separate persistence layer for the repository. Sub-modules:
#   user_db.py   -> user / payer store, persisted to backend/database/db/users.json
#                   (made available to the RAG pipeline for grounded, data-aware answers)
#   query_db.py  -> admin customer-care query store, persisted to backend/database/db/queries.json
#                   (answers from the RAG pipeline are recorded here for the admin dashboard)
#
# Re-exported here so the rest of the backend can simply do:
#   from app.database import get_user_db, get_query_db
from app.database.user_db import get_user_db
from app.database.query_db import get_query_db
