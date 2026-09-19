from flask import Flask, render_template, request, redirect
import os
import pandas as pd
from utils import BookRecommender
import atexit

app = Flask(__name__)

book_list = []
author_list = []
DATA_FOLDER = 'data'
AUTHORS_FILE = os.path.join(DATA_FOLDER, 'authors.txt')
BOOKS_FILE = os.path.join(DATA_FOLDER, 'titles.txt')
ALLOWED_EXTENSIONS = {'txt', 'csv', 'xlsx', 'xls'}

# Clear files on startup
def clear_data_files():
    if os.path.exists(BOOKS_FILE):
        os.remove(BOOKS_FILE)
    if os.path.exists(AUTHORS_FILE):
        os.remove(AUTHORS_FILE)

# Clear files on shutdown
def cleanup():
    clear_data_files()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Register cleanup function
atexit.register(cleanup)

# Clear on startup
clear_data_files()

# Rest of your code stays the same...
def load_from_files():
    books = []
    authors = []
    
    if os.path.exists(BOOKS_FILE):
        with open(BOOKS_FILE, 'r') as f:
            books = [line.strip() for line in f if line.strip()]
    
    if os.path.exists(AUTHORS_FILE):
        with open(AUTHORS_FILE, 'r') as f:
            authors = [line.strip() for line in f if line.strip()]
    
    return books, authors

book_list, author_list = load_from_files()

# Initialize lists from files
book_list, author_list = load_from_files()

# Function to save the lists to text files
def save_to_files(book_list, author_list):
    os.makedirs(DATA_FOLDER, exist_ok=True)
    
    with open(BOOKS_FILE, 'w') as f:
        for book in book_list:
            f.write(f"{book}\n")
    
    with open(AUTHORS_FILE, 'w') as f:
        for author in author_list:
            f.write(f"{author}\n")

@app.route('/', methods=["GET", 'POST'])
def homepage():
    book = None
    author = None

    if request.method == 'POST':
        book = request.form.get('book')  # Using .get() here
        author = request.form.get('author')  # Using .get() here

        if book and author:  # Ensure both book and author are not None or empty
            book_list.append(book)
            author_list.append(author)
            save_to_files(book_list, author_list)
            return redirect('/')  # Redirect to clear the form after submission
        
    return render_template('index.html', book=book, author=author, book_list=book_list, author_list=author_list)

def _find_column(columns, name):
    for col in columns:
        if col.strip().lower() == name:
            return col
    return None


def parse_book_file(file_storage):
    """Parse one uploaded file into a list of (title, author) pairs.

    .csv/.xlsx/.xls need 'title' and 'author' columns (case-insensitive).
    .txt needs one 'Title - Author' per line.
    """
    filename = file_storage.filename
    ext = filename.rsplit('.', 1)[1].lower()

    if ext == 'txt':
        content = file_storage.read().decode('utf-8')
        pairs = []
        for line in content.split('\n'):
            line = line.strip()
            if not line:
                continue
            if ' - ' not in line:
                raise ValueError(f"'{line}' in {filename} is not in 'Title - Author' format")
            title, author = line.split(' - ', 1)
            pairs.append((title.strip(), author.strip()))
        return pairs

    if ext == 'csv':
        df = pd.read_csv(file_storage)
    elif ext in ('xlsx', 'xls'):
        df = pd.read_excel(file_storage)
    else:
        raise ValueError(f"Unsupported file type: {filename}")

    title_col = _find_column(df.columns, 'title')
    author_col = _find_column(df.columns, 'author')
    if title_col is None or author_col is None:
        raise ValueError(f"{filename} must have 'title' and 'author' columns")

    df = df.dropna(subset=[title_col])
    return [
        (str(row[title_col]).strip(), str(row[author_col]).strip() if pd.notna(row[author_col]) else '')
        for _, row in df.iterrows()
    ]


@app.route('/upload', methods=['POST'])
def upload_files():
    try:
        files = [f for f in request.files.getlist('files') if f.filename]
        if not files:
            return "<h2> Please select at least one file. <a href='/'>Go back</a></h2>"

        for f in files:
            if not allowed_file(f.filename):
                return f"<h2> Unsupported file type: {f.filename}. <a href='/'>Go back</a></h2>"

        titles = []
        authors = []
        for f in files:
            for title, author in parse_book_file(f):
                titles.append(title)
                authors.append(author)

        # Add to existing lists
        book_list.extend(titles)
        author_list.extend(authors)
        save_to_files(book_list, author_list)

        return redirect('/')

    except Exception as e:
        return f"<h2> Error uploading files: {e}. <a href='/'>Go back</a></h2>"

@app.route('/delete', methods=['POST'])
def delete_entry():
    index = int(request.form.get('index'))  # Get the index of the entry to delete

    if 0 <= index < len(book_list):
        del book_list[index]
        del author_list[index]
        save_to_files(book_list, author_list)

    return redirect('/')

@app.route('/edit', methods=['GET', 'POST'])
def edit_entry():
    index = int(request.values.get('index'))

    if request.method == 'POST':
        updated_book = request.form['book']
        updated_author = request.form['author']
        book_list[index] = updated_book
        author_list[index] = updated_author
        save_to_files(book_list, author_list)
        return redirect('/')
    
    # GET request — load current values
    current_book = book_list[index]
    current_author = author_list[index]
    return render_template('edit.html', index=index, book=current_book, author=current_author)

@app.route('/recommend', methods=["GET"])
def recommend():
    try:
        # Check if titles and authors lists have content
        with open('data/titles.txt', 'r') as f_titles, open('data/authors.txt', 'r') as f_authors:
            titles = [line.strip() for line in f_titles if line.strip()]
            authors = [line.strip() for line in f_authors if line.strip()]

        if not titles or not authors:
            return "<h2>⚠️ You must enter at least one book and author before getting recommendations. <a href='/'>Go back</a></h2>"

        # Create recommender and get recommendations (Class that makes recommendations)
        recommender = BookRecommender(
            authors_path='data/authors.txt',
            titles_path='data/titles.txt',
            force_run=True 
        )
        
        recommendations = recommender.get_recommendations()
        return render_template("recommend.html", recommendations=recommendations.to_dict(orient='records'))

    except Exception as e:
        error_message = f"Error: {e}. Please enter more books."
        return render_template("error.html", message=error_message)

@app.route('/clear', methods=['POST'])
def clear_all():
    book_list.clear()
    author_list.clear()
    clear_data_files()
    save_to_files(book_list, author_list)
    return redirect('/')

if __name__ == '__main__':
    # app.run(debug=True)
    app.run(host='0.0.0.0', port=5000)