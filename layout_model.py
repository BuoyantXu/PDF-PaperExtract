import cv2
from doclayout_yolo import YOLOv10


# Load the pre-trained model
model = YOLOv10("F:\local_projects\PDF-PaperExtract\models", task="detect")

# Perform prediction
det_res = model.predict(
r"C:\Users\by242\Desktop\data\能源平台供应链可再生能源电力消纳激励契约研究_许书琴.pdf",
    imgsz=1024,        # Prediction image size
    conf=0.2,          # Confidence threshold
    device="cuda:0"    # Device to use (e.g., 'cuda:0' or 'cpu')
)

# Annotate and save the result
annotated_frame = det_res[0].plot(pil=True, line_width=5, font_size=20)
cv2.imwrite("result.jpg", annotated_frame)
