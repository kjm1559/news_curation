from transformers import pipeline
from typing import List, Dict, Optional

# Initialize the summarization pipeline.
# Using a smaller, faster model for demonstration purposes.
# For higher quality, consider models like 'bart-large-cnn' or 't5-large'.
# Note: This will download the model weights the first time it's run.
try:
    summarizer = pipeline("summarization", model="sshleifer/distilbart-cnn-6-6")
except Exception as e:
    print(f"Error initializing summarization pipeline: {e}")
    # Fallback or error handling
    summarizer = None

def summarize_article(text: str, max_length: int = 60, min_length: int = 10) -> Optional[str]:
    """
    Summarizes a given text article.
    
    Args:
        text (str): The full text of the article to summarize.
        max_length (int): The maximum length of the generated summary.
        min_length (int): The minimum length of the generated summary.
        
    Returns:
        Optional[str]: The summarized text, or None if summarization fails.
    """
    if summarizer is None:
        print("Summarization pipeline not available.")
        return None
        
    if not text or len(text.strip()) < min_length: # Basic check for short/empty text
        return text[:max_length] # Return truncated original text if too short to summarize

    try:
        # Truncate text if it's too long for the model
        # The exact max_position_embeddings depends on the model, but 1024 is common
        model_max_length = summarizer.model.config.max_position_embeddings
        if len(text) > model_max_length:
            text = text[:model_max_length]
            
        summary = summarizer(text, max_length=max_length, min_length=min_length, do_sample=False)
        return summary[0]['summary_text']
    except Exception as e:
        print(f"Error during summarization: {e}")
        return None

if __name__ == "__main__":
    # Example usage:
    print("Testing summarization module...")
    sample_text = """
    The Orbiter Discovery is scheduled to launch on Tuesday, March 8, 2011, at 3:52 p.m. EST from Kennedy Space Center in Florida.
    The STS-133 mission will deliver essential supplies and hardware to the International Space Station, including the Permanent Multipurpose Module (PMM) and a humanoid robot assistant.
    This will be the final flight of Discovery, one of NASA's three remaining space shuttles.
    The mission commander, Steven Lindsey, will lead a crew of six astronauts on this historic journey.
    The shuttle is expected to dock with the ISS on March 10 and return to Earth on March 18.
    Discovery has flown 38 missions to date, spending over 365 days in space and orbiting the Earth 5,830 times.
    Its contributions to space exploration have been immense, including the deployment of the Hubble Space Telescope.
    NASA is preparing for the retirement of the shuttle program later this year, shifting focus to new deep space exploration initiatives.
    """
    
    summary = summarize_article(sample_text)
    if summary:
        print(f"\nOriginal Text:\n{sample_text}")
        print(f"\nGenerated Summary:\n{summary}")
    else:
        print("Summarization failed.")
        
    # Test with empty text
    print("\nTesting with empty text:")
    empty_summary = summarize_article("")
    print(f"Summary for empty text: {empty_summary}")
    
    # Test with very short text
    print("\nTesting with short text:")
    short_text_summary = summarize_article("This is a very short sentence.", min_length=5)
    print(f"Summary for short text: {short_text_summary}")

