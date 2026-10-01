from flask import Flask, render_template, request, redirect
import pandas as pd
from utils.recommender import BookRecommender

app = Flask(__name__)

book_list = []
author_list = []
ALLOWED_EXTENSIONS = {'txt', 'csv', 'xlsx', 'xls'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def _dedupe_key(title, author):
    return (title.strip().lower(), author.strip().lower())


@app.route('/', methods=["GET", 'POST'])
def homepage():
    book = None
    author = None
    duplicate = False

    if request.method == 'POST':
        book = request.form.get('book')  # Using .get() here
        author = request.form.get('author')  # Using .get() here

        if book and author:  # Ensure both book and author are not None or empty
            existing = {_dedupe_key(b, a) for b, a in zip(book_list, author_list)}
            if _dedupe_key(book, author) in existing:
                duplicate = True
            else:
                book_list.append(book)
                author_list.append(author)
                return redirect('/')  # Redirect to clear the form after submission

    added = request.args.get('added', type=int)
    skipped = request.args.get('skipped', type=int)

    return render_template(
        'index.html', book=book, author=author, duplicate=duplicate,
        added=added, skipped=skipped,
        book_list=book_list, author_list=author_list,
    )

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
            # Split on the LAST ' - ' rather than the first: subtitled
            # titles commonly contain their own ' - ' (e.g. "Chip War - The
            # Fight for the World's Most Critical Technology"), but an
            # author name essentially never does.
            title, author = line.rsplit(' - ', 1)
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
            return render_template('error.html', message="Please select at least one file.")

        for f in files:
            if not allowed_file(f.filename):
                return render_template('error.html', message=f"Unsupported file type: {f.filename}.")

        existing = {_dedupe_key(b, a) for b, a in zip(book_list, author_list)}
        added = 0
        skipped = 0
        for f in files:
            for title, author in parse_book_file(f):
                key = _dedupe_key(title, author)
                if key in existing:
                    skipped += 1
                    continue
                existing.add(key)
                book_list.append(title)
                author_list.append(author)
                added += 1

        return redirect(f'/?added={added}&skipped={skipped}')

    except Exception as e:
        return render_template('error.html', message=f"Error uploading files: {e}")

@app.route('/delete', methods=['POST'])
def delete_entry():
    index = int(request.form.get('index'))  # Get the index of the entry to delete

    if 0 <= index < len(book_list):
        del book_list[index]
        del author_list[index]

    return redirect('/')

@app.route('/edit', methods=['GET', 'POST'])
def edit_entry():
    index = int(request.values.get('index'))

    if request.method == 'POST':
        book_list[index] = request.form['book']
        author_list[index] = request.form['author']
        return redirect('/')

    # GET request — load current values
    current_book = book_list[index]
    current_author = author_list[index]
    return render_template('edit.html', index=index, book=current_book, author=current_author)

@app.route('/recommend', methods=["GET"])
def recommend():
    try:
        if not book_list or not author_list:
            return render_template(
                'error.html',
                message="You must enter at least one book and author before getting recommendations.",
            )

        # Create recommender and get recommendations (Class that makes recommendations)
        recommender = BookRecommender(books=list(zip(book_list, author_list)), force_run=True)

        recommendations = recommender.get_recommendations()
        return render_template("recommend.html", recommendations=recommendations.to_dict(orient='records'))

    except Exception as e:
        error_message = f"Error: {e}. Please enter more books."
        return render_template("error.html", message=error_message)

@app.route('/clear', methods=['POST'])
def clear_all():
    book_list.clear()
    author_list.clear()
    return redirect('/')

if __name__ == '__main__':
    # app.run(debug=True)
    app.run(host='0.0.0.0', port=5001)
