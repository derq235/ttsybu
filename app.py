import time
from flask import Flask, render_template, request, jsonify, send_from_directory
import os
import edge_tts
import asyncio
import uuid
from pydub import AudioSegment

app = Flask(__name__)

# Folder to store audio files
OUTPUT_FOLDER = 'static/audio'
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# Dictionary to track progress (in-memory, for simplicity)
progress = {}


# Function to convert text to speech in chunks
async def convert_text_to_speech(task_id, text, voice_name, output_path):
    try:
        # Split the text into chunks if it's too long
        max_chunk_length = 4000  # Adjust this as needed based on API limits
        chunks = [text[i:i + max_chunk_length] for i in range(0, len(text), max_chunk_length)]

        audio_files = []
        total_chunks = len(chunks)

        for idx, chunk in enumerate(chunks):
            chunk_filename = f'{uuid.uuid4()}_{idx}.mp3'
            chunk_path = os.path.join(OUTPUT_FOLDER, chunk_filename)
            communicate = edge_tts.Communicate(chunk, voice_name)
            await communicate.save(chunk_path)
            audio_files.append(chunk_path)

            # Update progress
            progress[task_id] = int(((idx + 1) / total_chunks) * 100)

        # Combine audio chunks into a single file
        combined = AudioSegment.empty()
        for file in audio_files:
            audio = AudioSegment.from_mp3(file)
            combined += audio
            os.remove(file)  # Clean up temporary chunk file

        # Save the combined file
        combined.export(output_path, format="mp3")
        progress[task_id] = 100  # Mark progress as complete

    except Exception as e:
        progress[task_id] = -1  # Mark progress as failed
        print(f"Error during TTS conversion: {e}")
        raise


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/convert', methods=['POST'])
def convert():
    text = request.form['text']
    voice_name = request.form['voice_name']

    # Generate a unique filename and task ID
    output_filename = f'{uuid.uuid4()}.mp3'
    output_path = os.path.join(OUTPUT_FOLDER, output_filename)
    task_id = str(uuid.uuid4())
    progress[task_id] = 0  # Initialize progress

    try:
        # Run the asynchronous function in the background
        asyncio.run(convert_text_to_speech(task_id, text, voice_name, output_path))

        # Return the URL of the audio file and task ID
        audio_url = f'/audio/{output_filename}'
        return jsonify({'audioUrl': audio_url, 'taskId': task_id})

    except Exception as e:
        return jsonify({'error': 'Conversion failed', 'message': str(e)}), 500


@app.route('/progress/<task_id>')
def get_progress(task_id):
    """Endpoint to fetch the progress of a task."""
    if task_id in progress:
        return jsonify({'progress': progress[task_id]})
    return jsonify({'error': 'Task ID not found'}), 404


@app.route('/audio/<filename>')
def serve_audio(filename):
    try:
        return send_from_directory(OUTPUT_FOLDER, filename, as_attachment=True)
    except FileNotFoundError:
        return jsonify({'error': 'File not found'}), 404


if __name__ == '__main__':
    app.run(debug=True)
