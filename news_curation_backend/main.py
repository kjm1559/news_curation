import os
from fastapi import FastAPI, Depends, HTTPException, status, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from sqlalchemy import create_engine, Column, Integer, String, DateTime, REAL, ForeignKey
from datetime import datetime, timedelta
from passlib.context import CryptContext
from jose import JWTError, jwt
from typing import List, Dict, Optional
from pydantic import BaseModel, Field
import aiosqlite # Using aiosqlite for async database operations

from scraping import scrape_all_news # Import scraping function
from summarization import summarize_article # Import summarization function

# --- Database Setup ---
# Use an absolute path for the database to ensure it's created correctly
# relative to the project root, not the backend directory.
# This assumes the backend script is run from the news_curation_backend directory,
# and the db file should be at the same level as the backend directory.
# A better approach might be to pass DB path as an env var.
# For now, let's place it relative to the script's current location.
DB_FILE = "news_curation.db"
# Determine absolute path based on script location
script_dir = os.path.dirname(os.path.abspath(__file__))
DATABASE_URL = f"sqlite:///{os.path.join(script_dir, DB_FILE)}"

# Use async engine for aiosqlite
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# --- Database Models ---
class User(Base):
    __tablename__ = "users"
    user_id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password_hash = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

class NewsItem(Base):
    __tablename__ = "news_items"
    news_id = Column(Integer, primary_key=True, index=True)
    title = Column(String)
    url = Column(String, unique=True, index=True)
    source = Column(String)
    published_at = Column(DateTime, nullable=True)
    summary = Column(String)
    category = Column(String)
    scraped_at = Column(DateTime, default=datetime.utcnow)

class UserNewsInteraction(Base):
    __tablename__ = "user_news_interactions"
    interaction_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), index=True)
    news_id = Column(Integer, ForeignKey("news_items.news_id"), index=True)
    viewed_at = Column(DateTime, default=datetime.utcnow)
    interest_score = Column(REAL, default=1.0) # Represents current relevance, decays over time
    # category = Column(String) # Redundant if we can join with NewsItem, but useful if categories change

class UserPreference(Base):
    __tablename__ = "user_preferences"
    preference_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), index=True)
    category = Column(String)
    preference_level = Column(REAL, default=0.0) # Higher value means higher interest in this category

# Create tables if they don't exist
Base.metadata.create_all(bind=engine)

# --- Security Setup ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
# TODO: Load SECRET_KEY from environment variables
SECRET_KEY = os.environ.get("SECRET_KEY", "your-super-secret-key-change-me-in-prod")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Dependency to get database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Password verification
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

# Password hashing
def get_password_hash(password):
    return pwd_context.hash(password)

# Access token creation
def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# Security dependency to get current user
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_exception
    return user

# --- Pydantic Models ---
# Models for request bodies and responses

class UserRegister(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8) # Basic password strength

class UserResponse(BaseModel):
    user_id: int
    username: str
    created_at: datetime

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

# NewsItem Pydantic Models
class NewsItemBase(BaseModel):
    title: str
    url: str
    source: str
    published_at: Optional[datetime] = None
    summary: str
    category: str

class NewsItemCreate(NewsItemBase):
    pass

class NewsItemOut(NewsItemBase):
    news_id: int
    scraped_at: datetime

    class Config:
        from_attributes = True

# UserNewsInteraction Pydantic Models
class UserNewsInteractionBase(BaseModel):
    category: str

class UserNewsInteractionCreate(UserNewsInteractionBase):
    news_id: int

class UserNewsInteractionOut(BaseModel):
    interaction_id: int
    user_id: int
    news_id: int
    category: str
    viewed_at: datetime
    interest_score: float

    class Config:
        from_attributes = True

# UserPreference Pydantic Models
class UserPreferenceBase(BaseModel):
    category: str
    preference_level: float

class UserPreferenceCreate(UserPreferenceBase):
    pass

class UserPreferenceOut(UserPreferenceBase):
    preference_id: int
    user_id: int

    class Config:
        from_attributes = True

# --- FastAPI Application ---
app = FastAPI(title="News Curation API")

# --- CORS Configuration ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Background Tasks ---
def process_scraped_news(db: Session, scraped_data: List[Dict]):
    """Processes scraped news, summarizes them, and saves to DB."""
    for item_data in scraped_data:
        # Check if news item already exists
        existing_item = db.query(NewsItem).filter(NewsItem.url == item_data["url"]).first()
        if existing_item:
            continue # Skip if already processed

        # Summarize the article content (requires fetching full page, this is a placeholder)
        # In a real scenario, you'd need to fetch the full content from item_data["url"]
        # For this example, we'll assume we have the full text.
        # IMPORTANT: This is a critical part that needs robust implementation.
        # For now, let's mock a summary or indicate it needs full text fetching.
        article_text = "This is placeholder text for the full article content. In a real application, you would fetch the content from " + item_data['url'] + " and then summarize it." # TODO: Implement full content fetching and summarization
        
        summary = summarize_article(article_text) if article_text else "No summary available."
        
        db_news_item = NewsItem(
            title=item_data["title"],
            url=item_data["url"],
            source=item_data["source"],
            published_at=item_data.get("published_at"),
            summary=summary,
            category=item_data.get("category", "General"),
            scraped_at=item_data.get("scraped_at", datetime.utcnow())
        )
        db.add(db_news_item)
    db.commit()

def run_scraping_task(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Triggers the news scraping process."""
    print("Initiating background scraping task...")
    scraped_data = scrape_all_news()
    if scraped_data:
        background_tasks.add_task(process_scraped_news, db, scraped_data)
        return {"message": f"Scraping initiated. {len(scraped_data)} items found. Processing in background."}
    else:
        return {"message": "No new news found during scraping."}

# --- Authentication Endpoints ---
@app.post("/auth/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register_user(user: UserRegister, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == user.username).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already registered")
    hashed_password = get_password_hash(user.password)
    db_user = User(username=user.username, password_hash=hashed_password)
    db.add(db_user)
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error: {str(e)}")
    db.refresh(db_user)
    # Return basic user info, not password hash
    return UserResponse(user_id=db_user.user_id, username=db_user.username, created_at=db_user.created_at)

@app.post("/auth/login", response_model=Token)
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(data={"sub": user.username}, expires_delta=access_token_expires)
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/users/me", response_model=UserResponse)
def read_users_me(current_user: User = Depends(get_current_user)):
    # Return user info, exclude password hash
    return UserResponse(user_id=current_user.user_id, username=current_user.username, created_at=current_user.created_at)

# --- News Endpoints ---
@app.get("/news/categories", response_model=List[str])
def get_news_categories(db: Session = Depends(get_db)):
    # This should ideally fetch categories from a dedicated table or a predefined list
    # For now, let's get unique categories from existing news items, or a default list.
    categories = db.query(NewsItem.category).distinct().all()
    if not categories:
        return ["General", "Technology", "Sports", "Business", "Entertainment"] # Default categories
    return [cat[0] for cat in categories]

@app.get("/news/feed", response_model=List[NewsItemOut])
def get_news_feed(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 20
):
    # TODO: Implement personalized feed logic:
    # 1. Fetch user's preferred categories and their preference levels.
    # 2. Fetch recent news items, potentially filtered by preferred categories.
    # 3. Rank news items based on a combination of:
    #    - User's preference_level for the item's category.
    #    - User's interest_score from user_news_interactions (decayed for older items).
    #    - Recency of the news item.
    # 4. Return a ranked list of NewsItem objects.

    # For now, return most recent news items as a placeholder
    from sqlalchemy import desc
    recent_news = db.query(NewsItem).order_by(desc(NewsItem.published_at)).offset(skip).limit(limit).all()
    return recent_news

@app.get("/news/{news_id}", response_model=NewsItemOut)
def get_news_item(news_id: int, db: Session = Depends(get_db)):
    db_news = db.query(NewsItem).filter(NewsItem.news_id == news_id).first()
    if db_news is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="News item not found")
    return db_news

@app.post("/news/{news_id}/view", response_model=UserNewsInteractionOut)
def record_news_view(
    news_id: int,
    interaction_data: UserNewsInteractionCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Check if news item exists
    news_item = db.query(NewsItem).filter(NewsItem.news_id == news_id).first()
    if not news_item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="News item not found")

    # Record the interaction
    db_interaction = UserNewsInteraction(
        user_id=current_user.user_id,
        news_id=news_id,
        viewed_at=datetime.utcnow(),
        interest_score=1.0, # Initial score, will be decayed later
        category=interaction_data.category # Use category provided by user/frontend
    )
    db.add(db_interaction)
    db.commit()
    db.refresh(db_interaction)

    # Schedule interest score decay and preference updates in the background
    # This is a critical part of personalization, needs careful implementation
    background_tasks.add_task(update_user_interest_and_preferences, db, current_user.user_id, news_id, interaction_data.category)

    return db_interaction

# --- User Preference Endpoints ---
@app.get("/preferences", response_model=List[UserPreferenceOut])
def get_user_preferences(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    preferences = db.query(UserPreference).filter(UserPreference.user_id == current_user.user_id).all()
    return preferences

@app.post("/preferences", response_model=UserPreferenceOut)
def update_user_preference(
    preference: UserPreferenceCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Check if preference for this category already exists
    db_preference = db.query(UserPreference).filter(
        UserPreference.user_id == current_user.user_id,
        UserPreference.category == preference.category
    ).first()

    if db_preference:
        db_preference.preference_level = preference.preference_level
    else:
        db_preference = UserPreference(
            user_id=current_user.user_id,
            category=preference.category,
            preference_level=preference.preference_level
        )
        db.add(db_preference)
    
    db.commit()
    db.refresh(db_preference)
    return db_preference

# --- Background Task Logic for Interest Decay and Preference Update ---
def update_user_interest_and_preferences(db: Session, user_id: int, viewed_news_id: int, viewed_category: str):
    """
    Updates interest scores, decays older scores, and adjusts category preferences.
    This function runs in the background.
    """
    print(f"Running background task: Updating interest for user {user_id}, news {viewed_news_id}")
    
    # 1. Decay existing interest scores for the user
    # Items viewed long ago should have their score reduced.
    # This is a simplified decay. A more sophisticated approach might be time-based.
    decay_factor = 0.99 # Example decay factor per hour/day, needs tuning
    # For simplicity, let's just apply a fixed reduction or a decay based on days since viewed.
    # For a real system, this would involve a scheduled job that iterates through interactions.
    # For now, we'll just update the last viewed item's category preference.

    # 2. Adjust preference level for the category of the viewed news
    # If the user views news in a category, increase preference for that category.
    
    # Check if preference exists
    user_pref = db.query(UserPreference).filter(
        UserPreference.user_id == user_id,
        UserPreference.category == viewed_category
    ).first()

    if user_pref:
        # Increase preference level, cap at some max value
        user_pref.preference_level = min(user_pref.preference_level + 0.1, 10.0) # Increment and cap
    else:
        # Create new preference if category is new to the user
        user_pref = UserPreference(
            user_id=user_id,
            category=viewed_category,
            preference_level=1.0 # Initial preference for a newly viewed category
        )
        db.add(user_pref)
    
    db.commit()
    db.refresh(user_pref)
    print(f"Preference updated for category '{viewed_category}' to {user_pref.preference_level}")

    # Note: A true "decay" of interest_score would typically require a periodic job
    # that runs against all user_news_interactions. This POST endpoint focuses on
    # immediate feedback (preference update) and a single interaction record.
    # A separate scheduled task is needed for decay of older interest scores.

# --- Example Endpoint for Triggering Scraping ---
@app.post("/admin/scrape", status_code=status.HTTP_202_ACCEPTED)
def trigger_scrape(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Manually trigger the news scraping process."""
    return run_scraping_task(background_tasks, db)

# --- Main execution block (for running with uvicorn) ---
if __name__ == "__main__":
    import uvicorn
    # In a production environment, you'd use a more robust server like Gunicorn
    # and configure Uvicorn workers appropriately.
    # `reload=True` is useful for development.
    print("Starting FastAPI server...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
