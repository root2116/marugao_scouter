from flask import Flask, request, send_file
import io
from measure import evaluate_image, evaluate_image_with_segmentation
import cv2
import numpy as np
import zipfile
app = Flask(__name__)

@app.route('/')
def hello():
    return "Hello, World!"


@app.route('/upload', methods=['POST'])
def upload_file():
    if 'image' not in request.files:
        return "No file part", 400
    file = request.files['image']

    if file.filename == '':
        return "No selected file", 400

    # 画像の読み込み
    img = cv2.imdecode(np.fromstring(file.read(), np.uint8), cv2.IMREAD_COLOR)


    adjuested_processed_imgs, adjusted_scores = evaluate_image(img, is_adjusted=True)
    processed_imgs, scores = evaluate_image(img, is_adjusted=False)


    # Create a zip file in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
        # Add each processed image to the zip file
        for i, processed_img in enumerate(processed_imgs):
            # Convert the image to bytes
            _, img_bytes = cv2.imencode('.jpg', processed_img)
            # Add the image to the zip file with a unique name
            zip_file.writestr(f'processed_img_{i}.jpg', img_bytes.tobytes())

        for i, processed_img in enumerate(adjuested_processed_imgs):
            # Convert the image to bytes
            _, img_bytes = cv2.imencode('.jpg', processed_img)
            # Add the image to the zip file with a unique name
            zip_file.writestr(f'adjuested_processed_img_{i}.jpg', img_bytes.tobytes())
        

    # スコアをカンマ区切りでzipファイルのテキストファイルとして保存
    # スコアは少数第3位まで表示
    with zipfile.ZipFile(zip_buffer, 'a') as zip_file:
        data = "non-adjusted scores\n"
        data += '\n'.join([f'{score*100:.3f}' for score in scores])
        data += "\n"
        data += "adjusted scores\n"
        data += '\n'.join([f'{score*100:.3f}' for score in adjusted_scores])
        zip_file.writestr('scores.txt', data)
        
        
    


    # Set the position of the buffer to the beginning
    zip_buffer.seek(0)

    # Send the zip file to the client
    return send_file(zip_buffer, mimetype='application/zip', as_attachment=True, download_name='processed_images.zip')

@app.route('/upload2', methods=['POST'])
def upload_file2():
    if 'image' not in request.files:
        return "No file part", 400
    file = request.files['image']

    if file.filename == '':
        return "No selected file", 400

    # 画像の読み込み
    img = cv2.imdecode(np.fromstring(file.read(), np.uint8), cv2.IMREAD_COLOR)


    images, scores = evaluate_image_with_segmentation(img)
   


    # Create a zip file in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
        # Add each processed image to the zip file
        for i, processed_img in enumerate(images):
            # Convert the image to bytes
            _, img_bytes = cv2.imencode('.jpg', processed_img)
            # Add the image to the zip file with a unique name
            zip_file.writestr(f'processed_img_{i}.jpg', img_bytes.tobytes())
        

    # スコアをカンマ区切りでzipファイルのテキストファイルとして保存
    # スコアは少数第3位まで表示
    with zipfile.ZipFile(zip_buffer, 'a') as zip_file:
        data = "scores\n"
        data += '\n'.join([f'{score*100:.3f} ({inc*100:.3f}, {iou*100:.3f})' for (iou, inc, score) in scores])
        data += "\n"
        zip_file.writestr('scores.txt', data)
        
        
    


    # Set the position of the buffer to the beginning
    zip_buffer.seek(0)

    # Send the zip file to the client
    return send_file(zip_buffer, mimetype='application/zip', as_attachment=True, download_name='processed_images.zip')



if __name__ == '__main__':
    app.run(host="0.0.0.0", port=8000)
