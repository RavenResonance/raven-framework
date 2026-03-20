# AGENTS.md - Raven Framework

This file provides comprehensive documentation for AI coding agents working with the Raven Framework. It contains all essential information about components, API, patterns, and best practices for building gaze-based applications for Raven Glass.

## Project Overview

Raven Framework is a comprehensive UI framework and API for building gaze-based applications for Raven Glass. It provides:
- Gaze-based interactions (buttons, scrolling with eyes)
- Voice input
- Extensive sensor suite (eye tracking, cameras, IMUs, microphones)
- Modern UI components built on Python
- Media handling and AI integration

We are Raven Resonance, a small team building AR glasses for all-day wear. [Raven Glass v1](https://raven.computer/) hardware will be out soon and runs RavenOS, a Linux-based operating system. This repo contains a preview of Raven Framework and is the first part of the Raven SDK. We would love to hear your feedback in our [Discord community](https://raven.computer/s/discord)!

**Repository:** https://github.com/RavenResonance/raven-framework  
**Starter Projects:** https://github.com/RavenResonance/raven-starter-project

## Installation & Setup

### Prerequisites
- Python 3.10 or higher
- Git (for cloning the framework)

### Installation Steps

1. **Clone the Raven Framework:**
```bash
git clone https://github.com/RavenResonance/raven-framework.git 
cd raven-framework
pip install -e .
```

**Note:** Use `pip3 install -e .` instead of `pip install -e .` depending on your system.

**Try installing audio simulator support (recommended):**
```bash
pip install -e ".[audio-simulator]"
```
This installs `simpleaudio` for audio playback in simulator mode. Note that `simpleaudio` may not have pre-built binaries available for all Linux and Windows systems, which can cause installation to fail. If installation fails, don't worry - the framework will work without it, but audio playback won't be available in simulator mode (it will still work on Raven devices).

2. **Optional: Create a virtual environment:**
```bash
python -m venv raven-app
source raven-app/bin/activate  # macOS/Linux
# or
raven-app\Scripts\activate  # Windows
```

3. **Run an app:**
```bash
python main.py  # or python3 main.py
```

4. **Deploy to glasses:**
```bash
python main.py deploy
```

### Simulator Behavior

When running in simulator mode:
- **Cursor simulates eye gaze**: Cursor represents where you're looking (HID independent - mouse, trackpad, eye gaze, etc.)
- **Click simulates interaction**: Clicking simulates double blink or dwell-to-click
- **Black appears transparent**: Due to additive blending (waveguide display behavior)
- **Show Simulator button**: Click to preview how app looks on actual waveguide display
- **Closing windows**: Can close (X out of) either main app window or simulator window
- **Exiting app**: Click home icon in top right corner to exit

## Core App Structure

### Required Base Class

All Raven applications must inherit from `RavenApp`:

```python
from raven_framework.core.raven_app import RavenApp

class MyApp(RavenApp):
    def __init__(self, parent=None):
        super().__init__(parent)
        # self.app is a 640x640 container
        # Add widgets here
        self.app.add(widget)
```

### Entry Point

Always use `RunApp.run()` as the entry point:

```python
from raven_framework.core.run_app import RunApp

if __name__ == "__main__":
    RunApp.run(
        lambda: MyApp(),
        app_id="",
        app_key=""
    )
```

### Key Concepts
- Define a class that inherits from `RavenApp` - **required for all Raven applications**
- Name your main entry point file as `main.py`
- Use `RunApp.run()` to run the class you defined
- You get a 640x640 container called `self.app` that you can add widgets to
- You can create containers (like `VerticalContainer`) and add them to `self.app`
- You can add elements like buttons and text boxes to containers

## UI Widgets

**Note:** All components inherit from PySide6's `QWidget` class, so standard Qt methods like `hide()`, `show()`, `move()`, `resize()`, etc. are still available and work as expected.

### Layout Components

#### Container

Base container widget for organizing layout.

```python
from raven_framework.components.container import Container

# Simple container
container = Container()

# With fixed size
container = Container(width=640, height=640)

# With spacing
container = Container(spacing=10)

# With margins (uniform)
container = Container(inner_margin=20)

# With margins (horizontal, vertical)
container = Container(inner_margin=(30, 10))

# With margins (left, top, right, bottom)
container = Container(inner_margin=(20, 10, 20, 10))

# Adding widgets
container.add(button)  # Simple add
container.add(text_box, x=100, y=200)  # With absolute positioning
```

**Key params:** `width`, `height`, `background_color` (hex), `background_image` (path), `corner_radius`, `border_width`, `border_color`, `inner_margin`, `spacing`

**Key methods:** `add(widget, x=None, y=None)`, `clear()`

**Note:** Use `is_main_container=True` to inherit system themes (borders, positioning, sizing, fonts). For the main container of pages, **always** use `is_main_container=True`, `spacing=10`, and `inner_margin` (e.g. `inner_margin=(10, 15)` or `inner_margin=10`) so content has appropriate padding and the UI looks good.

#### VerticalContainer

Vertical layout container with automatic widget arrangement.

```python
from raven_framework.components.vertical_container import VerticalContainer

# Main page container: use spacing=10 and inner_margin for appropriate spacing
vbox = VerticalContainer(
    width=640,
    spacing=10,
    inner_margin=(10, 15),  # horizontal, vertical padding
    is_main_container=True,
)
# Prefer adding all widgets together in one .add() call
vbox.add(button1, button2, text_box)  # Stacks vertically
```

**Key params:** Same as Container

**Key methods:** `add(*widgets)`, `clear()`

**Note:** For the main container of pages, **always** use `is_main_container=True`, `spacing=10`, and `inner_margin` (e.g. `inner_margin=(10, 15)`) so content has appropriate padding. Prefer adding all widgets together in one `.add()` call instead of separate add functions.

#### HorizontalContainer

Horizontal layout container for side-by-side arrangement.

```python
from raven_framework.components.horizontal_container import HorizontalContainer

# Main page container: use spacing=10 and inner_margin for appropriate spacing
hbox = HorizontalContainer(
    width=640,
    spacing=10,
    inner_margin=(10, 15),
    is_main_container=True,
)
# Prefer adding all widgets together in one .add() call
hbox.add(icon1, icon2, icon3)  # Stacks horizontally
```

**Key params:** Same as Container

**Key methods:** `add(*widgets)`, `clear()`

**Note:** For the main container of pages, **always** use `is_main_container=True`, `spacing=10`, and `inner_margin` (e.g. `inner_margin=(10, 15)`). Prefer adding all widgets together in one `.add()` call instead of separate add functions.

### UI Components

#### TextBox

Text display widget with customizable styling.

```python
from raven_framework.components.text_box import TextBox

# Simple text
text = TextBox(text="Hello World")

# With alignment
text = TextBox(text="Hello World", width=400, alignment="center")  # left, center, right

# Custom styling
text = TextBox(text="Hello World", text_color="#FF0000", font_size=48)

# Using system fonts
text = TextBox(text="Display Text", font_type="display")
text = TextBox(text="Title Text", font_type="title")
text = TextBox(text="Headline Text", font_type="headline")
text = TextBox(text="Body Text", font_type="body")
text = TextBox(text="Small Text", font_type="small")
```

**Key params:** `font_type` (display/title/headline/body/small), `text_color` (hex), `font_size`, `font_weight`, `alignment`, `wrap_words`, `width`, `height`

**Key methods:** `set_text(new_text: str)`

**Note:** By default uses body font from theme. `font_type` applies theme's color, family, size, and weight automatically.

**Important:** Do not call `set_text()` on a TextBox after it has been destroyed, otherwise you'll get C++ binding errors. Always check if the widget still exists before updating text.

#### Button

Customizable button with dwell-to-click and scaling animations.

```python
from raven_framework.components.button import Button

# Simple button
button = Button(center_text="Click Me")

# Note: Buttons automatically adjust width and height based on text content.
# Only add width and height if absolutely needed.

# With custom size
button = Button(center_text="Click Me", width=150, height=60)

# With icon
button = Button(center_text="Click Me", icon_path="assets/icon.png")

# With action icon
button = Button(center_text="Click Me", show_action_icon=True, width=400)

# Click handlers
self.button = Button(center_text="Click Me")
self.button.on_clicked(self.on_button_click)

def on_button_click(self):
    self.button.set_text("Clicked!")

# With parameters
self.button.on_clicked(self.on_button_click, "New Text")

def on_button_click(self, new_text):
    self.button.set_text(new_text)
```

**Key params:** `width`, `height`, `background_color` (hex), `text_size`, `text_color` (hex), `font_weight`, `corner_radius`, `outline_width`, `outline_color`, `dwell_time`, `icon_path`, `disabled`

**Key methods:** `set_text(new_text: str)`, `on_clicked(callback, *args, **kwargs)`, `set_disabled(disabled: bool)`, `set_enabled(enabled: bool)`, `is_disabled() -> bool`

**Important:** Do not call `set_text()` on a Button after it has been destroyed, otherwise you'll get C++ binding errors. Always check if the widget still exists before updating text.

#### Icon

Circular or rounded-rect icon with dwell-click interaction.

```python
from raven_framework.components.icon import Icon

# Simple icon
icon = Icon(background_image_path="icon.png")

# With custom size
icon = Icon(background_image_path="icon.png", size=150)

# Click handlers
self.icon = Icon(size=80)
self.icon.on_clicked(self.on_icon_click)

def on_icon_click(self):
    self.icon.set_text("Clicked!")
```

**Key params:** `background_image_path`, `size`, `background_color` (hex), `center_text`, `text_size`, `text_color` (hex), `corner_radius`, `outline_width`, `outline_color`, `dwell_time`, `is_square`, `enable_click`, `bottom_text`, `disabled`

**Key methods:** `set_text(new_text: str)`, `on_clicked(callback, *args, **kwargs)`, `set_background_image(image_path: str)`, `set_disabled(disabled: bool)`, `set_enabled(enabled: bool)`, `is_disabled() -> bool`

#### Spacer

Simple spacer widget for adding empty space.

```python
from raven_framework.components.spacer import Spacer

spacer = Spacer(height=20)  # Vertical
spacer = Spacer(width=50)   # Horizontal
```

**Key params:** `width`, `height`

#### MediaViewer

Displays images, GIFs, or videos with rounded corners.

```python
from raven_framework.components.media_viewer import MediaViewer

# Image
viewer = MediaViewer(media_path="assets/image.jpg")

# Image (URL)
viewer = MediaViewer(media_path="https://example.com/image.jpg")

# GIF
viewer = MediaViewer(media_path="assets/animation.gif")

# Video
viewer = MediaViewer(media_path="assets/video.mp4", loop_video=True)
viewer.play_video()
viewer.pause_video()
```

**Key params:** `media_path` (local path or http(s) URL), `corner_radius`, `width`, `height`, `loop_video`, `scale_mode` ("cover" = fill widget and crop; "fit" = fit inside with letterbox; defaults to "cover")

**Key methods:** `play_video()`, `pause_video()`

**Note:** `width` and `height` must be multiples of 4 (QImage row stride requirement). If you pass other values (e.g. 385×385), the viewer will adjust them to the nearest multiple of 4 (e.g. 384×384) and log a warning. Use sizes like 384, 388, or 400 to avoid video corruption and the warning.

#### WebViewer

Displays web content.

```python
from raven_framework.components.web_viewer import WebViewer

web = WebViewer(url="https://example.com", width=300, height=200)
```

**Key params:** `url`, `width`, `height`

#### ScrollView

Scrollable widget with gaze-based dwell scrolling.

```python
from raven_framework.components.scroll_view import ScrollView

vbox = VerticalContainer(width=480, inner_margin=30)
for i in range(20):
    vbox.add(TextBox(f"This is line {i}."))
scroll = ScrollView(content_widget=vbox, width=480, height=720)

# With continuous scroll
scroll = ScrollView(content_widget=vbox, width=480, height=540, enable_continuous_scroll=True)
```

**Key params:** `content_widget`, `width`, `height`, `enable_continuous_scroll`

**Key methods:** `scroll_next()`, `scroll_prev()`, `start_auto_scroll()`, `stop_auto_scroll()`, `clear()`

#### ModelViewer

Displays 3D models from OBJ files with OpenGL rendering.

```python
from raven_framework.components.model_viewer import ModelViewer

viewer = ModelViewer(model_path="assets/model.obj", width=400, height=400)
```

**Note:** Raven Glass only supports OpenGL ES 2.0, not Vulkan or OpenGL ES 3.x. The ModelViewer automatically uses the appropriate OpenGL context based on the platform.

**Key params:** `model_path` (str), `width` (int), `height` (int)

### Cards

Reusable card components with various layouts.

#### TextCardWithButton

```python
from raven_framework.cards import TextCardWithButton

card = TextCardWithButton(
    text="Card text",
    button_text="Click Me",
    on_button_click=self.on_click,
    container_width=450
)
```

#### TextCardWithTwoButtons

```python
from raven_framework.cards import TextCardWithTwoButtons

card = TextCardWithTwoButtons(
    text="Card text",
    button_text_1="Button 1",
    button_text_2="Button 2",
    on_button_1_click=self.on_click_1,
    on_button_2_click=self.on_click_2,
    container_width=450
)
```

#### HorizontalTextCardWithButton

```python
from raven_framework.cards import HorizontalTextCardWithButton

card = HorizontalTextCardWithButton(
    text="Card text",
    button_text="Click Me",
    on_button_click=self.on_click,
    container_width=450
)
```

#### HorizontalTextCard

```python
from raven_framework.cards import HorizontalTextCard

card = HorizontalTextCard(
    text="Card text",
    container_width=450,
    text_alignment="center"
)
```

#### MediaCard

```python
from raven_framework.cards import MediaCard

card = MediaCard(
    image_path="assets/image.png",
    title_text="Title",
    subtitle_text="Subtitle",
    body_text="Body text",
    image_height=200,
    container_width=450
)
```

#### MediaCardWithButton

```python
from raven_framework.cards import MediaCardWithButton

card = MediaCardWithButton(
    image_path="assets/image.png",
    title_text="Title",
    subtitle_text="Subtitle",
    body_text="Body text",
    button_text="Click Me",
    on_button_click=self.on_click,
    image_height=200,
    container_width=450
)
```

#### MediaCardWithTwoButtons

```python
from raven_framework.cards import MediaCardWithTwoButtons

card = MediaCardWithTwoButtons(
    image_path="assets/image.png",
    title_text="Title",
    subtitle_text="Subtitle",
    body_text="Body text",
    button_text_1="Button 1",
    button_text_2="Button 2",
    on_button_1_click=self.on_click_1,
    on_button_2_click=self.on_click_2,
    image_height=200,
    container_width=450
)
```

#### ScrollableListCard

```python
from raven_framework.cards import ScrollableListCard

card = ScrollableListCard(
    title_text="List Title",
    info_strings=["Item 1", "Item 2", "Item 3"],
    button_strings=["View", "View", "View"],
    on_item_click=[
        (self.view_item, "Item 1"),
        (self.view_item, "Item 2"),
        (self.view_item, "Item 3")
    ],
    card_width=450,
    card_height=600
)
```

## Sensors

**Note:** All sensors require special entitlement for publishing apps (not for development). All sensors accept optional `app_id` and `app_key` parameters.

### Camera

```python
from raven_framework.peripherals.camera import Camera

camera = Camera()
camera.open_camera()
frame = camera.capture_camera_image()  # Returns ndarray | None
camera.close_camera()
```

**Methods:**
- `open_camera() -> VideoCapture | None`
- `capture_camera_image() -> ndarray | None`
- `close_camera() -> None`

### Microphone

```python
from raven_framework.peripherals.microphone import Microphone

mic = Microphone()
mic.start_recording()
wav_bytes = mic.stop_recording()  # Returns bytes
level = mic.get_level()  # Returns float (0.0 to 1.0)
```

**Methods:**
- `start_recording() -> None`
- `stop_recording() -> bytes`
- `get_level() -> float`

### IMU

**Note:** In simulator mode, arrow keys can be used to simulate accelerometer readings. Use Up/Down arrow keys for Y-axis acceleration and Left/Right arrow keys for X-axis acceleration.

```python
from raven_framework.peripherals.imu import IMU

imu = IMU()
reading = imu.get_reading()  # Returns dict | None
if reading:
    accel = reading.get("accelerometer")
    gyro = reading.get("gyroscope")
```

**Methods:**
- `get_reading() -> dict | None` (contains accelerometer, gyroscope, magnetometer)

### EyeTracker

**Note:** Cannot be simulated in simulator mode.

```python
from raven_framework.peripherals.eye_tracker import EyeTracker

tracker = EyeTracker()
position = tracker.get_gaze_position()  # Returns Tuple[int, int] | None
if position:
    x, y = position
```

**Methods:**
- `get_gaze_position() -> Tuple[int, int] | None`

### Speaker

**Note:** In simulator mode, audio playback requires the `audio-simulator` optional dependency. Install it with `pip install -e ".[audio-simulator]"` or `pip install simpleaudio`. Note that `simpleaudio` may not have pre-built binaries available for all Linux and Windows systems, which can cause installation to fail. If `simpleaudio` is not available, the framework will log a warning and audio playback will not work in simulator mode (but will still work on Raven devices).

```python
from raven_framework.peripherals.speaker import Speaker

speaker = Speaker()
speaker.play_audio(wav_bytes, on_finished=callback)
speaker.stop_audio()
```

**Methods:**
- `play_audio(wav_bytes: bytes, on_finished: Callable | None = None) -> None`
- `stop_audio() -> None`

### ClickButton

**Note:** Cannot be simulated in simulator mode.

```python
from raven_framework.peripherals.click_button import ClickButton

button = ClickButton()
if button.is_pressed():
    print("Button is pressed")
pressed = button.wait_for_press(timeout=5.0)
```

**Methods:**
- `is_pressed() -> bool`
- `wait_for_press(timeout: float = 5.0) -> bool`

**Note:** Additional peripheral support, including spatial microphone and sound processing, and enhanced click button controls, will be added in future releases of the framework.

## Utilities

### Routine

Timer-based task execution for periodic or delayed execution.

```python
from raven_framework.helpers.routine import Routine

# Delay routine (single shot)
self.delay = Routine(interval_ms=5000, invoke=self.on_done, mode="delay")

def on_done(self):
    print("Done")

# Periodic routine
self.routine = Routine(interval_ms=1000, invoke=self.on_tick, mode="repeat")

def on_tick(self):
    print("Tick")

# Stop routine
self.routine.stop()
```

**Params:** `interval_ms` (int), `invoke` (Callable), `mode` ("repeat" or "delay"), `parent` (QObject, optional)

**Methods:** `stop() -> None`

### Animation Utilities

Simple animation functions for fading widgets.

```python
from raven_framework.helpers.animation_utils import fade_in, fade_out

# Simple fade in
fade_in(my_widget)

# Fade out
fade_out(my_widget)

# Custom parameters
fade_in(my_widget, duration=750)
```

**Note:** Call these functions at the end of `__init__` for best results.

**Functions:**
- `fade_in(widget, start_value=0.0, end_value=1.0, duration=750) -> None`
- `fade_out(widget, start_value=1.0, end_value=0.0, duration=750) -> None`

### AsyncRunner

Asynchronous task runner using Qt's thread pool.

```python
from raven_framework.helpers.async_runner import AsyncRunner

runner = AsyncRunner()

def long_task():
    # Do heavy work here
    return result

def on_complete(result):
    # Update UI on main thread
    pass

runner.run(long_task, on_complete=on_complete)
```

**Important:** Do not update UI components (like buttons or text boxes) directly from background threads. Always update UI components in the `on_complete` callback, which runs on the main thread. Updating UI from separate threads can cause crashes or undefined behavior.

**Methods:**
- `run(func: Callable, on_complete: Callable | None = None) -> None`

### OpenAiHelper

Helper class for OpenAI API integration.

```python
from raven_framework.helpers.open_ai_helper import OpenAiHelper

ai = OpenAiHelper(open_ai_key="my_open_ai_key")

# Text response
response = ai.get_text_response("Hello, how are you?")

# Transcribe audio
text = ai.transcribe_audio(wav_bytes)

# Multimodal (text + image)
response = ai.process_multimodal_with_image("What's in this image?", image_frame)

# Text to speech
audio_bytes = ai.generate_tts("Hello world", voice="alloy")
```

**Params:** `open_ai_key` (str)

**Methods:**
- `transcribe_audio(wav_bytes: bytes, model: str = "whisper-1", audio_filename: str = "audio.wav", audio_mime_type: str = "audio/wav") -> str`
- `get_text_response(prompt: str, model: str = "gpt-4o") -> str`
- `process_multimodal_with_image(prompt: str, image: ndarray, model: str = "gpt-4o") -> str`
- `generate_tts(text: str, model: str = "tts-1", voice: str = "alloy", response_format: str = "wav") -> bytes`

## Hardware Specifications

Raven Glass v1 hardware specifications:

* **Operating System:** RavenOS (Linux-based)
* **Processor:** Quad-core 64-bit ARM processor
* **Graphics:** GPU with OpenGL ES 2.0 support
* **Display:** 30 degree diagonal FoV, full-color waveguide display on the right eye
* **Primary Input:** Eye control sensors
* **Connectivity:** WiFi & Bluetooth
* **Audio Input:** Multiple microphones
* **Audio Output:** 2 downward-facing speakers
* **Camera:** World-facing camera
* **Motion Sensors:** IMU
* **Power:** Raven Wings™ hot-swappable batteries
* **Indicators:** Beakon™ lights
* **Environmental Sensors:** Ambient light and proximity sensors

## Design Guidelines

**CRITICAL:** These guidelines are essential for creating comfortable, usable applications on Raven Glass. Follow them strictly.

### Core Design Philosophy

Raven Glass is designed for **comfort, presence, and real-world awareness**. The UI should feel ambient, optional, and calm. If the UI feels distracting, it's failing.

**Key Principles:**
- **Minimize everything**: Use very little text, minimal content, and very few buttons (only if absolutely needed)
- **Minimize interactions**: Reduce the number of clicks/taps users need to perform - every interaction has a cost
- **Right-side placement**: Place elements primarily on the **right side** of the UI
- **Peripheral by default**: Design for the periphery - move content to central focus only when user intentionally engages
- **Less is more**: When in doubt, remove elements rather than add them

### Display Specifications
- **Resolution:** 720 × 720 LCOS
- **Field of View:** 30° diagonal
- **Offset:** Right-eye
- The right-side offset reduces distraction and preserves central vision - designs should assume **asymmetry**

### Color & Waveguide
- Raven uses **waveguide-based additive display**
- Light from display adds to real-world light
- **Black appears transparent** - pure black cannot be displayed (though can be used for occlusion/depth)
- White text/UI elements work well against dark backgrounds
- White and saturated colors provide the strongest contrast against real world backgrounds
- Apply accent colors sparingly to preserve contrast and readability
- Never rely on color alone for meaning
- All color appearance depends on ambient lighting, display brightness, and waveguide properties

### Typography & Content

**Text Guidelines:**
- **Use minimal text** - don't use a lot of text
- Prefer system fonts only
- We suggest a visual angle range of **0.8° to 1.2°**, and **Title, Headline, and Body** fall within this range
- For Raven Glass (720×720 display with 30° diagonal FOV), these translate to the following pixel values:
  - **Title** - 38px (1.12° visual angle)
  - **Headline** - 33px (0.97° visual angle)
  - **Body** - 28px (0.83° visual angle)
  - **Display** - 45px (1.33° visual angle) - use sparingly
  - **Small** - 18px (0.53° visual angle) - use sparingly
- Use Display and Small fonts only when necessary
- Don't stack multiple text sizes in tight areas
- Keep text concise and scannable
- Avoid long paragraphs or dense text blocks
- Use text only and only if necessary

**Content Guidelines:**
- **Not a lot of content** - keep content minimal and focused
- Show only what's immediately necessary
- Use pagination or progressive disclosure rather than showing everything at once
- Prioritize clarity over completeness
- Always add appropriate margins and spacings so UI looks good.

### Layout & Spacing (Required for Main Containers)

**Agents must apply these rules whenever building a page or screen:**

- **Main containers:** Any `Container`, `VerticalContainer`, or `HorizontalContainer` that wraps the primary content of a page/screen must use:
  - `spacing=10` (consistent gap between child widgets)
  - `inner_margin` so content is not flush to edges — use e.g. `inner_margin=(10, 15)` (horizontal, vertical) or `inner_margin=10` (uniform)
  - `is_main_container=True` when using theme inheritance
- **Do not** add cards or content directly to `self.app` without wrapping them in a container that has `inner_margin` and `spacing=10`; otherwise the layout will look cramped and unpolished.
- **Example:** When a screen shows only a single card, wrap that card in a `VerticalContainer` with `spacing=10`, `inner_margin=(10, 15)`, and `is_main_container=True`, then add the container to `self.app`.

### Layout Principles

**Spatial Model:**
- Layout is based on **attention, not symmetry**
- **Place interactive elements primarily on the right side** - this is critical for comfort and avoiding accidental activation
- Avoid controls in primary reading areas
- Assume accidental gaze is common
- For critical actions (like home, scroll pagination), place in top right or right periphery to avoid accidental activation
- Users tend to look at bottom center most frequently - avoid placing rarely clicked items there

**Central vs Peripheral Zones:**
- **Central**: Reading and focus-heavy content only
- **Peripheral**: Persistent background content, buttons, interactive controls, elements not triggered by users

### Interaction & Controls

**Button Guidelines:**
- **Use very few buttons, only if you need them** - every button adds cognitive load
- **Minimize the number of clicks users have to do** - design workflows to require as few interactions as possible
- Use large targets (avoid dense layouts)
- Eye tracking: ~2–3° accuracy - account for this in target sizing
- **Dwell-to-click** (default) - gaze at button for set duration
- **Double-blink** (default) - double blink to activate focused elements
- Prefer voice input for longer responses rather than multiple button clicks

**Scrolling & Navigation:**
- Pagination is **strongly recommended** over scrolling - it minimizes eye movement and interaction cost
- Traditional scrolling is discouraged due to eye fatigue and attention shifts
- Use [scroll view](#scrollview) only when scrolling is absolutely necessary
- Auto-scroll may work for passive content but requires visual tracking and can reduce comfort

### Best Practices Summary

**DO:**
- ✅ Place buttons and interactive elements on the right side
- ✅ Use minimal text and content
- ✅ Minimize the number of clicks/interactions required
- ✅ Use pagination over scrolling
- ✅ Design for peripheral awareness
- ✅ Use system fonts and theme colors
- ✅ Keep UI calm and ambient
- ✅ Use `spacing=10` and `inner_margin` (e.g. `inner_margin=(10, 15)`) on all main page containers so layouts have appropriate spacing

**DON'T:**
- ❌ Use a lot of text or dense content
- ❌ Add buttons unless absolutely necessary
- ❌ Require multiple clicks for common actions
- ❌ Place critical actions in bottom center
- ❌ Use custom fonts (especially on buttons)
- ❌ Create dense, cluttered layouts
- ❌ Rely on color alone for meaning
- ❌ Omit `inner_margin` or `spacing` on main containers (content will look flush and cramped)

## Complete Example Applications

### Hello World

```python
# Import the necessary components from the Raven Framework
from raven_framework import RavenApp, RunApp, TextBox, VerticalContainer


# Define your app class, inheriting from RavenApp (required for all Raven apps)
class HelloWorld(RavenApp):
    # Initialize the app
    def __init__(self, parent=None) -> None:
        # Call the parent class constructor to set up the app
        super().__init__(parent)
        # Create a vertical container with a width of 640 pixels
        # VerticalContainer automatically stacks widgets vertically
        vbox = VerticalContainer(width=640)
        # Create a text box with "Hello, World!" text
        # width=640 makes it span the container width
        # alignment="center" centers the text horizontally
        text_box = TextBox("Hello, World!", width=640, alignment="center")
        # Add the text box to the vertical container
        vbox.add(text_box)
        # Add the container to the main app window (self.app is a 640x640 container)
        self.app.add(vbox)


# Entry point - run the app when this script is executed
if __name__ == "__main__":
    # Launch the app using RunApp.run()
    # lambda: HelloWorld() creates a new instance of the app
    # app_id="" and app_key="" are empty for simulator mode
    RunApp.run(lambda: HelloWorld(), app_id="", app_key="")
```

### Stopwatch

```python
# Imports
from enum import Enum

# Raven Framework Imports
from raven_framework import RavenApp, Routine, RunApp, fade_in
from raven_framework.components.cards import TextCardWithButton, TextCardWithTwoButtons

# Constants - maximum time to display, container width, and font size
MAX_TIME = 3600
CONTAINER_WIDTH = 450
DISPLAY_FONT_SIZE = 38


# Helper function to convert seconds to MM:SS format
def seconds_to_time_string(seconds: int) -> str:
    # Check if time exceeds maximum
    if seconds > MAX_TIME:
        return "Max time reached"
    # Calculate minutes by integer division
    minutes = seconds // 60
    # Calculate remaining seconds using modulo
    seconds = seconds % 60
    # Format as MM:SS with zero-padding
    return f"{minutes:02d}:{seconds:02d}"


# Enum to represent the different states of the stopwatch
class AppState(Enum):
    """Application state enumeration."""

    # Stopwatch is actively counting
    RUNNING = "running"
    # Stopwatch is paused (time preserved)
    PAUSED = "paused"
    # Stopwatch is stopped
    STOPPED = "stopped"


# Application
class Stopwatch(RavenApp):
    """Stopwatch application with start, pause, resume, and reset functionality."""

    def __init__(self, parent=None) -> None:
        """Initialize the Stopwatch application."""
        # Call parent constructor to set up the app
        super().__init__(parent)
        # Initialize app state to stopped
        self.app_state = AppState.STOPPED
        # Initialize elapsed time to 0 seconds
        self.elapsed_time = 0
        # Routine will be created when stopwatch starts
        self.stopwatch_routine = None
        # Initialize the UI
        self.init_ui()
        # Fade in animation for smooth appearance
        fade_in(self.app)

    def init_ui(self):
        """Initialize the UI based on the current application state."""
        # Clear the app to remove any existing widgets
        self.app.clear()
        self.main_container = None

        # Create different UI based on current state
        if self.app_state == AppState.STOPPED:
            if self.elapsed_time > 0:
                # If time exists, show Resume and Reset buttons
                self.main_container = TextCardWithTwoButtons(
                    text=seconds_to_time_string(self.elapsed_time),
                    button_text_1="Resume",
                    button_text_2="Reset",
                    on_button_1_click=self.start_stopwatch,
                    on_button_2_click=self.reset_stopwatch,
                    text_alignment="center",
                    text_font_size=DISPLAY_FONT_SIZE,
                    container_width=CONTAINER_WIDTH,
                )
            else:
                # If no time, show Start button only
                self.main_container = TextCardWithButton(
                    text="00:00",
                    button_text="Start",
                    on_button_click=self.start_stopwatch,
                    text_alignment="center",
                    text_font_size=DISPLAY_FONT_SIZE,
                    container_width=CONTAINER_WIDTH,
                )
        elif self.app_state == AppState.RUNNING:
            # When running, show Pause and Stop buttons
            self.main_container = TextCardWithTwoButtons(
                text=seconds_to_time_string(self.elapsed_time),
                button_text_1="Pause",
                button_text_2="Stop",
                on_button_1_click=self.pause_stopwatch,
                on_button_2_click=self.stop_stopwatch,
                text_alignment="center",
                text_font_size=DISPLAY_FONT_SIZE,
                container_width=CONTAINER_WIDTH,
            )
        elif self.app_state == AppState.PAUSED:
            # When paused, show Resume and Stop buttons
            self.main_container = TextCardWithTwoButtons(
                text=seconds_to_time_string(self.elapsed_time),
                button_text_1="Resume",
                button_text_2="Stop",
                on_button_1_click=self.resume_stopwatch,
                on_button_2_click=self.stop_stopwatch,
                text_alignment="center",
                text_font_size=DISPLAY_FONT_SIZE,
                container_width=CONTAINER_WIDTH,
            )
        else:
            print("Error: Invalid app state")
            self.main_container = None

        # Add the container to the app, positioned at the right edge
        self.app.add(
            self.main_container, x=self.app.width() - self.main_container.width(), y=0
        )

    def start_stopwatch(self):
        """Start the stopwatch from stopped state."""
        # Change state to running
        self.app_state = AppState.RUNNING
        # Create a routine that calls update_stopwatch every 1000ms (1 second)
        self.stopwatch_routine = Routine(
            interval_ms=1000,
            invoke=self.update_stopwatch,
        )
        # Update UI to show running state
        self.init_ui()

    def pause_stopwatch(self):
        """Pause the stopwatch while preserving elapsed time."""
        # Change state to paused
        self.app_state = AppState.PAUSED
        # Stop the routine if it exists
        if self.stopwatch_routine:
            self.stopwatch_routine.stop()
            self.stopwatch_routine = None
        # Update UI to show paused state
        self.init_ui()

    def resume_stopwatch(self):
        """Resume the stopwatch from paused state."""
        # Change state to running
        self.app_state = AppState.RUNNING
        # Create a new routine to continue counting
        self.stopwatch_routine = Routine(
            interval_ms=1000,
            invoke=self.update_stopwatch,
        )
        # Update UI to show running state
        self.init_ui()

    def stop_stopwatch(self):
        """Stop the stopwatch and return to stopped state without resetting time."""
        # Change state to stopped (but keep the time)
        self.app_state = AppState.STOPPED
        # Stop the routine if it exists
        if self.stopwatch_routine:
            self.stopwatch_routine.stop()
            self.stopwatch_routine = None
        # Update UI to show stopped state
        self.init_ui()

    def reset_stopwatch(self):
        """Reset the stopwatch to 00:00 and stop if running."""
        # Reset elapsed time to 0
        self.elapsed_time = 0
        # Stop the routine if it exists
        if self.stopwatch_routine:
            self.stopwatch_routine.stop()
            self.stopwatch_routine = None
        # Change state to stopped
        self.app_state = AppState.STOPPED
        # Update UI to show reset state
        self.init_ui()

    def update_stopwatch(self):
        """Update the stopwatch display (called by routine every second)."""
        # Increment elapsed time by 1 second
        self.elapsed_time += 1
        # Convert to formatted string
        updated_string = seconds_to_time_string(self.elapsed_time)
        # Update the text in the UI
        self.main_container.text_box.set_text(updated_string)


if __name__ == "__main__":
    RunApp.run(lambda: Stopwatch(), app_id="", app_key="")
```

### Art Studio

```python
# Imports
from dataclasses import dataclass
from enum import Enum

# Raven Framework Imports
from raven_framework import (
    Button,
    RavenApp,
    RunApp,
)
from raven_framework.components.media_viewer import MediaViewer
from raven_framework.components.cards import ScrollableListCard


# Data Classes
@dataclass
class Painting:
    """Data class for painting information."""

    # Name of the painting
    title: str
    # File path to the image
    path: str
    # Width and height of the image
    resolution: tuple[int, int]


# Constants
# Dictionary containing all available paintings
PAINTINGS = {
    "Apple": Painting(title="Apple", path="paintings/apple.png", resolution=(400, 600)),
    "Pear": Painting(title="Pear", path="paintings/pear.png", resolution=(400, 600)),
    "Candle": Painting(
        title="Candle", path="paintings/candle.png", resolution=(400, 600)
    ),
    "Mug": Painting(title="Mug", path="paintings/mug.png", resolution=(400, 600)),
    "Sky": Painting(title="Sky", path="paintings/sky.png", resolution=(400, 600)),
    "Sunset": Painting(
        title="Sunset", path="paintings/sunset.png", resolution=(400, 600)
    ),
}


# Enums
class AppState(Enum):
    """Application state enumeration."""

    # Showing the list of paintings
    PAINTING_LIST = "painting_list"
    # Showing a single painting
    PAINTING_VIEW = "painting_view"


# Application
class ArtStudio(RavenApp):
    """Oil painting reference viewer for learning basic objects."""

    def __init__(self, parent=None) -> None:
        """Initialize the ArtStudio application."""
        # Call parent constructor to set up the app
        super().__init__(parent)
        # Store all paintings
        self.paintings = PAINTINGS
        # Start in list view
        self.app_state = AppState.PAINTING_LIST
        # No painting selected initially
        self.selected_painting = None
        # Initialize the UI
        self.init_ui()

    def init_ui(self) -> None:
        """Initialize the UI based on the current application state."""
        # Clear the app to remove any existing widgets
        self.app.clear()

        if self.app_state == AppState.PAINTING_LIST:
            # Create list of painting titles for display
            info_strings = [painting.title for painting in self.paintings.values()]
            # Create "View" button for each painting
            button_strings = ["View"] * len(info_strings)
            # Create click handlers for each item - each calls view_painting with the painting name
            on_item_click = [
                (self.view_painting, painting.title)
                for painting in self.paintings.values()
            ]
            # Create a scrollable list card with all paintings
            card = ScrollableListCard(
                title_text="Learn oil painting",
                info_strings=info_strings,
                button_strings=button_strings,
                on_item_click=on_item_click,
            )
            # Add the card to the app
            self.app.add(card)
        elif self.app_state == AppState.PAINTING_VIEW:
            # Validate that the selected painting exists
            if self.selected_painting not in self.paintings:
                # If not found, go back to list view
                self.app_state = AppState.PAINTING_LIST
                print(
                    f"Selected painting {self.selected_painting} not found in paintings"
                )
                self.go_back()
                return

            # Get the painting data
            painting = self.paintings[self.selected_painting]

            # Create a media viewer to display the painting image
            painting_viewer = MediaViewer(
                media_path=painting.path,
                width=painting.resolution[0],
                height=painting.resolution[1],
            )

            # Create a back button to return to the list
            back_button = Button(
                center_text="Back",
            )
            # Set the click handler to go back to list
            back_button.on_clicked(self.go_back)

            # Add the painting viewer, positioned at the right edge
            self.app.add(
                painting_viewer, x=self.app.width() - painting.resolution[0], y=0
            )
            # Add the back button, positioned at bottom right
            self.app.add(
                back_button,
                x=self.app.width() - back_button.width(),
                y=painting.resolution[1] - 30,
            )

    def switch_state(self, new_state: AppState) -> None:
        """Switch the application to a new state and update the UI accordingly."""
        # Change the app state
        self.app_state = new_state
        # Reinitialize UI to reflect the new state
        self.init_ui()

    def view_painting(self, painting_name: str) -> None:
        """Navigate to painting view."""
        # Store the selected painting name
        self.selected_painting = painting_name
        # Switch to painting view state
        self.switch_state(AppState.PAINTING_VIEW)

    def go_back(self) -> None:
        """Return to painting list view."""
        # Clear the selected painting
        self.selected_painting = None
        # Switch back to list view state
        self.switch_state(AppState.PAINTING_LIST)


if __name__ == "__main__":
    RunApp.run(lambda: ArtStudio(), app_id="", app_key="")
```

### Simple AI App

```python
# Import Raven Framework components
from raven_framework import AsyncRunner, RavenApp, RunApp
from raven_framework.components.cards import TextCardWithButton
from raven_framework.helpers.open_ai_helper import OpenAiHelper
from raven_framework.peripherals.camera import Camera
from raven_framework.peripherals.microphone import Microphone
from raven_framework.peripherals.speaker import Speaker

# OpenAI API key - set this or load from environment variable
OPEN_AI_KEY = ""  # Enter open ai key here or load from env


class SimpleAiApp(RavenApp):
    def __init__(self, parent=None) -> None:
        # Call parent constructor to set up the app
        super().__init__(parent)
        # Create a card with a button for user interaction
        self.card_container = TextCardWithButton(
            text="Ask me anything about what you're looking at!",
            on_button_click=self.on_button_click,
        )
        # Add the card to the app, positioned at the right edge
        self.app.add(
            self.card_container, x=(self.app.width() - self.card_container.width()), y=0
        )
        # Set initial button text
        self.card_container.button.set_text("Start")
        # Initialize sensor and helper objects as None (lazy initialization)
        self.camera = None
        self.agent = None
        self.mic = None
        self.speaker = None
        self.async_runner = None
        # Track recording state
        self.is_recording = False

    def on_button_click(self):
        """Toggle recording and process with AI when button is clicked."""
        if self.is_recording:
            # If currently recording, stop and process
            self.stop_recording_and_process()
        else:
            # If not recording, start recording
            self.start_recording()

    def start_recording(self):
        """Start recording audio from microphone."""
        # Initialize microphone if not already done
        if not self.mic:
            self.mic = Microphone()

        # Start recording audio
        self.mic.start_recording()
        # Update state
        self.is_recording = True
        # Update UI to show recording state
        self.card_container.button.set_text("Stop")
        self.card_container.button.set_enabled(True)
        self.card_container.text_box.set_text("Recording... Click again to stop!")
        print("Recording started")

    def stop_recording_and_process(self):
        """Stop recording, transcribe, process with image, and play response."""
        # Check if microphone is initialized
        if not self.mic:
            self.card_container.text_box.set_text("Error: Microphone not initialized")
            self.card_container.button.set_enabled(True)
            return

        # Stop recording and get audio bytes
        wav_bytes = self.mic.stop_recording()
        # Update state
        self.is_recording = False
        # Update button text
        self.card_container.button.set_text("Start")

        # Check if audio was actually recorded
        if not wav_bytes:
            self.card_container.text_box.set_text("No audio recorded. Try again.")
            self.card_container.button.set_enabled(True)
            print("No audio recorded")
            return

        print(f"Audio recorded, {len(wav_bytes)} bytes")
        # Update UI to show processing state
        self.card_container.text_box.set_text("Processing...")
        self.card_container.button.set_text("...")
        self.card_container.button.set_disabled(True)

        # Initialize OpenAI helper if not already done
        if not self.agent:
            if OPEN_AI_KEY == "":
                print("Open AI Key missing")
                return
            self.agent = OpenAiHelper(OPEN_AI_KEY)

        # Initialize camera if not already done
        if not self.camera:
            self.camera = Camera()

        # Initialize speaker if not already done
        if not self.speaker:
            self.speaker = Speaker()

        # Initialize async runner if not already done
        if not self.async_runner:
            self.async_runner = AsyncRunner()

        # Define async function to process AI (runs in background thread)
        def run_ai():
            try:
                # Step 1: Transcribe the audio to text using Whisper
                text = self.agent.transcribe_audio(wav_bytes)
                print(f"Transcribed text: {text}")

                # Step 2: Capture image from camera
                frame = self.camera.capture_camera_image_and_close()

                if frame is None:
                    # If no image available, use text-only response
                    response = self.agent.get_text_response(
                        f"{text} (Reply as short as possible)"
                    )
                    print("No camera image, using text-only response")
                else:
                    # Step 3: Process image with transcribed text using multimodal model
                    prompt = f"{text} (Reply as short as possible)"
                    response = self.agent.process_multimodal_with_image(
                        prompt=prompt, image=frame
                    )
                    print(f"AI response: {response}")

                # Step 4: Store the response and generate text-to-speech audio
                self.ai_response = response
                self.ai_audio_bytes = self.agent.generate_tts(response)

            except Exception as e:
                # Handle any errors during processing
                print(f"Failed to process: {e}")
                self.ai_response = f"Error: {str(e)}"
                self.ai_audio_bytes = None

        # Define callback to update UI and play audio (runs on main thread)
        def on_complete():
            # Update UI with the AI response
            if hasattr(self, "ai_response"):
                self.card_container.text_box.set_text(self.ai_response)
                # Play the audio response if available
                if hasattr(self, "ai_audio_bytes") and self.ai_audio_bytes:
                    self.speaker.play_audio(self.ai_audio_bytes)
            # Reset button state
            self.card_container.button.set_text("Start")
            self.card_container.button.set_enabled(True)

        # Run AI processing asynchronously (won't block the UI)
        self.async_runner.run(run_ai, on_complete=on_complete)


if __name__ == "__main__":
    RunApp.run(lambda: SimpleAiApp(), app_id="", app_key="")
```

## Code Style & Conventions

### File Structure
- Main entry point must be named `main.py`
- All apps must inherit from `RavenApp`
- Use `RunApp.run()` as entry point

### Import Patterns
```python
# Standard imports first
from enum import Enum
from dataclasses import dataclass

# Raven Framework core imports
from raven_framework.core.raven_app import RavenApp
from raven_framework.core.run_app import RunApp
from raven_framework.components.button import Button
from raven_framework.components.text_box import TextBox
from raven_framework.components.vertical_container import VerticalContainer

# Raven Framework utilities
from raven_framework.helpers.routine import Routine
from raven_framework.helpers.async_runner import AsyncRunner
from raven_framework.helpers.animation_utils import fade_in

# Raven Framework cards
from raven_framework.cards import TextCardWithButton

# Raven Framework sensors (heavier imports)
from raven_framework.peripherals.camera import Camera
from raven_framework.peripherals.microphone import Microphone

# Raven Framework helpers
from raven_framework.helpers.open_ai_helper import OpenAiHelper
```

### Naming Conventions
- Class names: PascalCase (e.g., `MyApp`, `Stopwatch`)
- Method names: snake_case (e.g., `on_button_click`, `init_ui`)
- Constants: UPPER_SNAKE_CASE (e.g., `MAX_TIME`, `CONTAINER_WIDTH`)

### State Management
- Use enums for application states
- Store state in instance variables
- Call `init_ui()` to refresh UI when state changes

### Best Practices
- Always call `super().__init__(parent)` in `__init__`
- Use `self.app.clear()` before rebuilding UI
- Position widgets at right edge: `x=self.app.width() - widget.width()`
- Use `spacing=10` and `inner_margin` (e.g. `inner_margin=(10, 15)`) on main page containers so content has appropriate padding
- Use `AsyncRunner` for heavy operations to avoid blocking UI
- Initialize sensors lazily (only when needed)
- Use `fade_in()` at end of `__init__` for smooth appearance
- Always provide `app_id` and `app_key` for deployment

## Testing & Running

### Simulator Mode
```bash
python main.py
# or
python3 main.py
```

### Deployment Mode
```bash
python main.py deploy
# or
python3 main.py deploy
```

**Note:** Deployment requires valid `app_id` and `app_key` in `RunApp.run()`.

## Common Patterns

### Adding a Button with Click Handler
```python
from raven_framework.core.raven_app import RavenApp
from raven_framework.core.run_app import RunApp
from raven_framework.components.button import Button
from raven_framework.components.vertical_container import VerticalContainer

class MyApp(RavenApp):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        vbox = VerticalContainer(width=640)
        # Create a button with text
        button = Button(center_text="Click Me")
        # Set what happens when the button is clicked
        button.on_clicked(self.on_button_click)
        vbox.add(button)
        self.app.add(vbox)
    
    # Define the click handler function
    def on_button_click(self):
        print("Button was clicked!")

if __name__ == "__main__":
    RunApp.run(lambda: MyApp(), app_id="", app_key="")
```

### Creating a Repeat Routine
```python
from raven_framework.core.raven_app import RavenApp
from raven_framework.core.run_app import RunApp
from raven_framework.helpers.routine import Routine
from raven_framework.components.text_box import TextBox
from raven_framework.components.vertical_container import VerticalContainer

class MyApp(RavenApp):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        vbox = VerticalContainer(width=640)
        # Create a text box to display the counter
        self.counter_text = TextBox("Counter: 0", width=640, alignment="center")
        vbox.add(self.counter_text)
        self.app.add(vbox)
        
        # Initialize counter
        self.counter = 0
        
        # Create a routine that repeats every 1000ms (1 second)
        self.routine = Routine(
            interval_ms=1000,  # Run every 1000 milliseconds
            invoke=self.update_counter,  # Call this function each time
            mode="repeat"  # Repeat mode (runs continuously)
        )
    
    # Function called by the routine
    def update_counter(self):
        self.counter += 1
        self.counter_text.set_text(f"Counter: {self.counter}")

if __name__ == "__main__":
    RunApp.run(lambda: MyApp(), app_id="", app_key="")
```

## Additional Resources

- **Framework Repository:** https://github.com/RavenResonance/raven-framework
- **Starter Projects:** https://github.com/RavenResonance/raven-starter-project
- **AGENTS.md Standard:** https://agents.md/

## License

This project is proprietary software. The Raven Framework code and documentation are proprietary and may not be redistributed, modified, or used except as expressly permitted by RavenResonance. Do not push the Raven Framework code to public repositories or distribute it without authorization.

