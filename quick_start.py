
import os
from utils import BookRecommender



# Create sample data if it doesn't exist
def setup_sample_data():
    """Create sample data files if they don't exist."""
    os.makedirs('data', exist_ok=True)
    
    if not os.path.exists('data/titles.txt'):
        titles = [
            "The Great Gatsby",
            "1984",
            # "To Kill a Mockingbird",
            # "Pride and Prejudice",
            # "Harry Potter and the Philosopher's Stone"
        ]
        with open('data/titles.txt', 'w') as f:
            f.write('\n'.join(titles))
        print("Created data/titles.txt")
    
    if not os.path.exists('data/authors.txt'):
        authors = [
            "F. Scott Fitzgerald",
            "George Orwell",
            # "Harper Lee",
            # "Jane Austen",
            # "J.K. Rowling"
        ]
        with open('data/authors.txt', 'w') as f:
            f.write('\n'.join(authors))
        print("Created data/authors.txt")


# Main execution
if __name__ == "__main__":
    print("Book Recommender - Quick Start")
    print("=" * 50)
    print()
    
    # Setup data
    setup_sample_data()
    print()
    
    # Create recommender
    print("Initializing BookRecommender...")
    recommender = BookRecommender(
        authors_path="data/authors.txt",
        titles_path="data/titles.txt",
        force_run=True  # Set to False to use cache
    )
    
    # Get recommendations
    print("Getting book recommendations...")
    print("(This may take a moment while fetching from Google Books API)")
    print()
    
    recommendations = recommender.get_recommendations()
    
    # Display results
    print("=" * 50)
    print("RECOMMENDED BOOKS:")
    print("=" * 50)
    print(recommendations.to_string(index=False))
    print()
    print("Done! ✓")



