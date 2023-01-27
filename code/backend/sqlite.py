from backend.common import Document, Bookmark
import sqlite3

# SQLite3 backend, stores data in a local .db file
class BackendSQLite:
    # The database location
    database: str

    # Errors will be propagated to the object's creator
    def __init__(self, database: str):
        # Initialize the database and get a cursor
        connection = sqlite3.connect(database)
        cursor = connection.cursor()

        # Create the users table if it doesn't exist
        cursor.execute('''CREATE TABLE IF NOT EXISTS users
                          (username text, userkey text)''')
        # Create the documents table if it doesn't exist
        cursor.execute('''CREATE TABLE IF NOT EXISTS documents
                          (username text, document text, progress text,
                           percentage float, device text, device_id text,
                           timestamp int)''')

        # Create the Bookmarks table if it doesn't exist
        cursor.execute('''CREATE TABLE IF NOT EXISTS bookmarks
                          (id int primary key, title text, url text)''')
        # Commit and free the cursor and connection
        cursor.close()
        connection.commit()
        connection.close()

        # Save the database file location
        self.database = database

    # Adds a username/userkey combination.
    # Returns False if the user already exists.
    def create_user(self, username: str, userkey: str):
        connection = sqlite3.connect(self.database)
        cursor = connection.cursor()

        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        if cursor.fetchone():
            # Attempted to add a user that already exists
            return False

        # Let's add the user:
        cursor.execute("INSERT INTO users VALUES (?, ?)", (username, userkey))

        # Cleanup
        cursor.close()
        connection.commit()
        connection.close()

        return True

    # Create or update a bookmark
    def update_bookmark(self, mark: Bookmark):
        connection = sqlite3.connect(self.database)
        cursor = connection.cursor()

        print(vars(mark))
        cursor.execute("SELECT * FROM bookmarks where id = ?", (mark.id,))
        if cursor.fetchone():
            cursor.execute('''UPDATE bookmarks
                              SET title = ?, url = ? 
                              WHERE id = ?''',
                           (mark.title, mark.url, mark.id))
        else:    
            cursor.execute("INSERT INTO bookmarks VALUES (?, ?, ?)",
                           (mark.id, mark.title, mark.url))
        # Cleanup
        cursor.close()
        connection.commit()
        connection.close()

# class Bookmark:
#    id: int
#    title: str
#    url: str


    # Updates a document, creating if it does not exist.
    def update_document(self, username: str, document: Document):
        connection = sqlite3.connect(self.database)
        cursor = connection.cursor()
        
        # If the document doesn't exist, let's create it.
        cursor.execute("SELECT * FROM documents WHERE username = ? AND document = ?", (username, document.document))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?, ?)",
                           (username, document.document, document.progress, document.percentage,
                            document.device, document.device_id, document.timestamp))

        # If the document _does_ exist, update it.
        cursor.execute('''UPDATE documents
                          SET progress = ?, percentage = ?, device = ?, device_id = ?, timestamp = ?
                          WHERE username = ? AND document = ?''',
                       (document.progress, document.percentage, document.device, document.device_id,
                        document.timestamp, username, document.document))

        # Cleanup
        cursor.close()
        connection.commit()
        connection.close()

    # Checks if a login is valid.
    # Returns True if it is, False if not.
    def check_login(self, username: str, userkey: str) -> bool:
        connection = sqlite3.connect(self.database)
        cursor = connection.cursor()

        # Check if the username/userkey combo exists.
        cursor.execute("SELECT * FROM users WHERE username = ? AND userkey = ?", (username, userkey))
        exists = bool(cursor.fetchone())

        # Cleanup
        cursor.close()
        connection.commit()
        connection.close()

        # Return our result
        return exists

    def get_bookmark(self, mark_id: int) -> Bookmark:
        connection = sqlite3.connect(self.database)
        cursor = connection.cursor()
        cursor.execute("SELECT * from bookmarks WHERE id = ?", (mark_id,))
        row = cursor.fetchone()
        if not row:
            return None
        mark = Bookmark(row[0], row[1], row[2])
        # Cleanup
        cursor.close()
        connection.commit()
        connection.close()
        return mark

    # Gets the details of a document present in the database.
    # Returns None if it doesn't exist.
    def get_document(self, username: str, document: str) -> Document:
        connection = sqlite3.connect(self.database)
        cursor = connection.cursor()

        # Get the relevant row in the table
        cursor.execute("SELECT * FROM documents WHERE username = ? AND document = ?", (username, document))
        row = cursor.fetchone()
        if not row:
            # Document isn't present in the database
            return None

        # Create a document instance from it
        resultdoc = Document(row[1], row[2], row[3], row[4], row[5], row[6])

        # Cleanup
        cursor.close()
        connection.commit()
        connection.close()

        return resultdoc

    # Prints the database to the console.
    # Intended for debugging.
    def dbg_print_database(self):
        connection = sqlite3.connect(self.database)
        cursor = connection.cursor()

        # Print the users table
        print("------ Table 'users' ------")
        for row in cursor.execute("SELECT * FROM users"):
            print(row)

        # Print the documents table
        print("\n------ Table 'documents' ------")
        for row in cursor.execute("SELECT * FROM documents"):
            print(row)

        # Cleanup
        cursor.close()
        connection.close()

