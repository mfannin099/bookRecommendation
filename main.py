from flask import Flask, render_template, request, redirect
import os

app = Flask(__name__)

book_list = []
author_list = []
DATA_FOLDER = 'data'
AUTHORS_FILE = os.path.join(DATA_FOLDER, 'authors.txt')
BOOKS_FILE = os.path.join(DATA_FOLDER, 'titles.txt')

# Function to save the lists to text files
def save_to_files(book_list, author_list):
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

@app.route('/another_page')
def another_page():
    return "<h2>This is another page</h2>"

if __name__ == '__main__':
    app.run(debug=True)