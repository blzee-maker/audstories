import sys
from audio_engine.utils.logger import get_logger
from audio_engine.renderer import TimelineRenderer

logger = get_logger(__name__)

def main():
    if len(sys.argv) < 3:
        print("Usage: python main.py <timeline.json> <output.wav>")
        print("Example: python main.py shadowless.json output/shadowless/final.wav")
        sys.exit(1)
    
    timeline_path = sys.argv[1]
    output_path = sys.argv[2]
    
    logger.info(f"Starting audio rendering: {timeline_path} -> {output_path}")
    renderer = TimelineRenderer()
    renderer.render(
        timeline_path=timeline_path,
        output_path=output_path
    )
    logger.info("Audio rendered successfully!")

if __name__ == "__main__":
    main()
