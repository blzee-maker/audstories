from audio_engine.renderer import TimelineRenderer

renderer = TimelineRenderer()
renderer.render_streaming(
    timeline_path="shadowless.json",
    output_path="output/shadowless/streaming.wav"
)
print("✓ Streaming render complete!")