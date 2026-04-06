<p align="center">
    <img src="./docs/logo-AI4VisualNovel.png" alt="logo" width="55%">
</p>
<h3 align="center">
<b>AI4VisualNovel: A Role-Play Driven Multi-Agent Framework for
Topological Branching Narrative Generation and Visual Synthesis in Visual
Novel</b>
</h3>

`AI4VisualNovel` is an end-to-end framework specifically designed for **creating high-quality, multi-branch visual novels via a role-play driven multi-agent system**.
You only need to input your requirement, and the framework will generate the final game.

Unlike prior approaches that focus on linear narrative generation or struggle with cross-modal consistency, `AI4VisualNovel` proposes a **Topological Sort-based DAG (Directed Acyclic Graph) mechanism** , which allows for **causally consistent** non-linear storytelling and complex plot branching management. This design makes `AI4VisualNovel` **highly robust for generating long-form, immersive interactive narratives** where player choices genuinely impact the story direction.

`AI4VisualNovel` introduces a **novel "Actor Agent" paradigm** that participates in both dialogue generation and visual auditing. By simulating a professional studio pipeline (Producer, Writer, Actor, Artist) , it enables the generation of **persona-aligned character sprites** and authentic dialogue, ensuring that visual assets strictly adhere to character settings rather than generic descriptions. The framework directly outputs **playable game**, bridging the gap between LLM creativity and executable interactive media.

## 📰 News
- [2026.03] The framework now supports custom original characters—bring your OC to life and create a story that is truly your own!
- [2026.01] Code released! The paper is coming soon...


## 📺 Output Game Preview
<p align="center">
  <img src="./docs/A.png" width="45%" />
  <img src="./docs/B.png" width="45%" />
</p>


## 🏗️ Framework Overview
<p align="center">
    <img src="./docs/workflow.png" alt="framework" width="100%">
</p>


## 🛠️ Installation

Follow these steps to set up your development environment:

1.  **Clone the Repository**:
    ```bash
    git clone https://github.com/ttsmallHot/AI4VisualNovel.git
    cd AI4VisualNovel
    ```

2.  **Install Dependencies**:
    ```bash
    conda create -n AI4VisualNovel python=3.10
    conda activate AI4VisualNovel
    pip install -r requirements.txt
    ```

3.  **Configure Environment**:
    Fill in the parameters in the `.env` file as instructed before starting.

---

## 🎮 Visual Novel Generation & Execution

### 1. Story Generation
Start the multi-agent collaboration to generate world settings, story graph, scripts, and visual assets. You can provide your requirements via a text file example as follows:

```yaml
requirements:
  file_path: data/1.txt

oc:
  characters:
    - id: Nanami
      name: Nanami
      gender: female
      is_protagonist: true
      personality: ""
      appearance: ""
      background: ""
      neutral_image_path: data/images/characters/Nanami/neutral.png
```

```bash
# Generate by phases (recommended)
python main.py --mode design --input-file input.yaml
python main.py --mode script
python main.py --mode render

# Or generate with empty requirements (AI will decide everything)
python main.py --mode design
python main.py --mode script
python main.py --mode render
```
*   **Outputs**: Generated files are stored in `data` folder, including scripts and images.
*   **Design phase note**: `design` uses a two-step pipeline — Step1 generates outline (`story_outline.groups`), Step2 generates `story_graph` and writes it to `data/story_graph.json`.

### 2. Play the Game
Execute the built-in Pygame-based engine to experience the generated story:
```bash
python main.py --mode play
```
*Note: You can also utilize other game engines (e.g., Unity, Ren'Py) to load the formatted data in the `data` folder for a more polished user experience.*

### 3. Export to Ren'Py 

```bash
# Export Ren'Py project from existing generated data
python main.py --mode export-renpy
```

After running this command, the required `script.rpy` and corresponding asset files will be generated in the `renpy_export` folder. Copy them into your Ren'Py project directory to run the game.

### 3. Packaging & Distribution
If you want to distribute your Pygame masterpiece, build a standalone executable to share your game.

- **For Windows**:
  ```batch
  pyinstaller --onefile --windowed --name "AI4VisualNovel" --add-data "data;data" main.py
  ```
- **For macOS**:
  ```bash
  pyinstaller --onefile --windowed --name "AI4VisualNovel" --add-data "data:data" main.py
  ```

## 📜 License
This project is licensed under the [Apache License 2.0](LICENSE).
  

