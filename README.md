# News Curation Project

This is a comprehensive news curation platform designed to collect, summarize, and provide a personalized news feed for users.

## Project Structure

*   **`news_curation_backend/`**: A FastAPI-based backend that handles:
    *   News scraping from various sources.
    *   Natural language processing (summarization) of articles.
    *   User authentication and profile management.
    *   Personalized news feed generation based on user preferences.
*   **`news_curation_frontend/`**: A Flutter-based mobile application providing:
    *   User registration and login.
    *   A personalized news feed.
    *   Preference management (user interests).
    *   Detailed article viewing.

## Getting Started

1.  **Backend Setup**:
    *   Navigate to `news_curation_backend/`.
    *   Ensure all dependencies (e.g., FastAPI, Transformers, SQLAlchemy) are installed in your virtual environment.
    *   Run the backend using `uvicorn main:app`.

2.  **Frontend Setup**:
    *   Navigate to `news_curation_frontend/`.
    *   Ensure Flutter SDK is installed.
    *   Run the application using `flutter run`.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
