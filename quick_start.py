from utils import BookRecommender

BOOKS = [
    ("The Great Gatsby", "F. Scott Fitzgerald"),
    ("1984", "George Orwell"),
    # ("To Kill a Mockingbird", "Harper Lee"),
    # ("Pride and Prejudice", "Jane Austen"),
    # ("Harry Potter and the Philosopher's Stone", "J.K. Rowling"),
]


if __name__ == "__main__":
    print("Book Recommender - Quick Start")
    print("=" * 50)
    print()

    print("Initializing BookRecommender...")
    recommender = BookRecommender(
        books=BOOKS,
        force_run=True  # Set to False to use cache
    )

    print("Getting book recommendations...")
    print("(This may take a moment while fetching from Open Library)")
    print()

    recommendations = recommender.get_recommendations()

    print("=" * 50)
    print("RECOMMENDED BOOKS:")
    print("=" * 50)
    print(recommendations.to_string(index=False))
    print()
    print("Done! ✓")
