import json
import os
import shutil

import torch
from doclayout_yolo import YOLOv10
from pdf2image import convert_from_path


def predict_with_yolov10(model_path, image_path, imgsz=1024, conf=0.2, device='cpu'):
    """
    使用 YOLOv10 模型进行预测并返回检测结果。
    """
    # 加载模型
    model = YOLOv10(model_path)

    # 进行预测
    det_res = model.predict(
        image_path,
        imgsz=imgsz,
        conf=conf,
        device=device,
    )

    # 提取检测结果
    detections = []
    for detection in det_res[0].boxes:
        bbox = detection.xyxy.tolist()[0]  # 边界框坐标 [x_min, y_min, x_max, y_max]
        confidence = detection.conf.item()  # 置信度
        class_id = int(detection.cls.item())  # 类别 ID
        class_name = model.names[class_id]  # 类别名称
        detections.append({
            "bbox": bbox,
            "confidence": confidence,
            "class_id": class_id,
            "class_name": class_name
        })

    return detections


def process_pdf_layout(pdf_path, model_path, res_path='outputs', imgsz=1024, conf=0.2):
    """
    解析 PDF 文件的布局并导出 layout.json 文件。
    """
    # 确保输出目录存在
    if not os.path.exists(res_path):
        os.makedirs(res_path)

    # 将 PDF 转换为图像
    images = convert_from_path(pdf_path, dpi=300)  # dpi 设置分辨率

    # 自动选择设备
    device = 'cuda' if torch.cuda.is_available() else 'mps' if torch.backends.mps.is_available() else 'cpu'
    print(f"Using device: {device}")

    # 存储所有页面的布局信息
    layout_data = []

    # 处理每一页图像
    for i, image in enumerate(images):
        # 构建临时图像路径
        temp_image_path = os.path.join(res_path, f"page_{i + 1}.jpg")

        # 保存临时图像文件
        image.save(temp_image_path, "JPEG")

        # 调用 YOLOv10 模型进行预测
        detections = predict_with_yolov10(
            model_path=model_path,
            image_path=temp_image_path,
            imgsz=imgsz,
            conf=conf,
            device=device
        )

        # 构建当前页面的布局信息
        page_layout = {
            "page_number": i + 1,
            "detections": detections
        }
        layout_data.append(page_layout)

        # 删除临时图像文件（可选）
        os.remove(temp_image_path)

    # 导出 layout.json 文件
    json_output_path = os.path.join(res_path, "layout.json")
    with open(json_output_path, "w", encoding="utf-8") as json_file:
        json.dump(layout_data, json_file, indent=4)

    print(f"Layout data exported to {json_output_path}")


# 示例调用
if __name__ == "__main__":
    # 定义参数
    paper_title = "Acquisitions-of-start-ups-by-incumbent-businesses--A-market-se_2016_Research"
    path_paper = f"F:/local_projects/RP-p-hacking/tmp_files/{paper_title}/origin.pdf"

    model_path = "models/doclayout_yolo_docstructbench_imgsz1024.pt"
    # 将pdf复制到outputs文件夹下
    os.makedirs(f"outputs/{paper_title}", exist_ok=True)

    shutil.copy(path_paper, f"outputs/{paper_title}/origin.pdf")

    res_path = f"outputs/{paper_title}"  # 输出目录
    imgsz = 1024  # 图像大小
    conf = 0.2  # 置信度阈值

    # 调用函数
    process_pdf_layout(path_paper, model_path, res_path, imgsz, conf)
