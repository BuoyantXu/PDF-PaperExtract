import json
import os

import torch
from PIL import Image
from huggingface_hub import login
from transformers import AutoImageProcessor, AutoModelForObjectDetection

# Clear HF_TOKEN environment variable
if "HF_TOKEN" in os.environ:
    del os.environ["HF_TOKEN"]

# Set proxy (if needed)
os.environ["HTTP_PROXY"] = "http://127.0.0.1:7890"
os.environ["HTTPS_PROXY"] = "http://127.0.0.1:7890"

# Login to Hugging Face
login("***")


def process_table_structure(image_path, output_path):
    # Load image
    image = Image.open(image_path).convert("RGB")

    # Initialize structure recognition model and processor
    processor = AutoImageProcessor.from_pretrained("microsoft/table-transformer-structure-recognition")
    model = AutoModelForObjectDetection.from_pretrained("microsoft/table-transformer-structure-recognition")

    # Process image
    inputs = processor(images=image, return_tensors="pt")

    # Model inference
    with torch.no_grad():
        outputs = model(**inputs)

    # Process predictions
    target_sizes = torch.tensor([image.size[::-1]])
    results = processor.post_process_object_detection(outputs, threshold=0.7, target_sizes=target_sizes)[0]

    # Extract table structure
    table_structure = {
        'rows': [],
        'columns': [],
        'cells': []
    }

    # Map predictions to structure
    for box, score, label in zip(results["boxes"], results["scores"], results["labels"]):
        box = [round(i, 2) for i in box.tolist()]
        label_name = model.config.id2label[label.item()]
        confidence = round(score.item(), 3)

        structure_item = {
            "bbox": box,
            "confidence": confidence,
            "class_name": label_name
        }

        if "row" in label_name:
            table_structure["rows"].append(structure_item)
        elif "column" in label_name:
            table_structure["columns"].append(structure_item)
        elif "cell" in label_name:
            table_structure["cells"].append(structure_item)

    # Sort rows and columns by position
    table_structure["rows"].sort(key=lambda x: x["bbox"][1])  # Sort by y-coordinate
    table_structure["columns"].sort(key=lambda x: x["bbox"][0])  # Sort by x-coordinate

    # Save results to JSON file
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(table_structure, f, indent=4, ensure_ascii=False)

    return table_structure


# Process the image and save results
image_path = r"***"
output_path = r"***"
table_structure = process_table_structure(image_path, output_path)

image = Image.open(image_path)

# Save cropped columns
for i, column in enumerate(table_structure['columns']):
    x1, y1, x2, y2 = column['bbox']
    column_image = image.crop((x1, y1, x2, y2))
    column_image = column_image.convert('RGB')
    column_image.save(f"column_{i + 1}.jpg")

# Save cropped rows
for i, column in enumerate(table_structure['rows']):
    x1, y1, x2, y2 = column['bbox']
    row_image = image.crop((x1, y1, x2, y2))
    row_image = row_image.convert('RGB')
    row_image.save(f"row_{i + 1}.jpg")
