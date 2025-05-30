import sys, os
import rawpy
from pathlib import Path
import OpenEXR
import numpy as np

from PySide6.QtWidgets import (QApplication, QLabel, QPushButton,
                               QVBoxLayout, QMainWindow, QProgressBar, QLineEdit, QRadioButton, QGroupBox, QWidget, QHBoxLayout, QMessageBox, QFileDialog)
from PySide6.QtCore import Slot, Qt, Signal, QThread

class ConversionThread(QThread):
    progress_updated = Signal(int, str)
    conversion_finished = Signal(bool, str)
    
    def __init__(self, input_path, output_path, is_batch=False):
        super().__init__()
        self.input_path = input_path
        self.output_path = output_path
        self.is_batch = is_batch
        self.cancel_requested = False
        
    def run(self):
        try:
            if self.is_batch:
                self.batch_convert()
            else:
                self.convert_single()
            self.conversion_finished.emit(True, "Conversion completed successfully!")
        except Exception as e:
            self.conversion_finished.emit(False, f"Error: {str(e)}")
            
    def convert_single(self):
        input_file = Path(self.input_path)
        
        # Determine output path
        if not self.output_path:  # No output specified - use same dir as input
            output_file = input_file.with_suffix('.exr')
        else:
            output_path = Path(self.output_path)
            if output_path.is_dir():  # Output is a directory - keep original filename
                output_file = output_path / (input_file.stem + '.exr')
            else:  # Output is a specific file path
                output_file = output_path
        
        self.progress_updated.emit(0, f"Converting {input_file.name}...")
        try:
            self.rw2_to_exr(str(input_file), str(output_file))
            self.progress_updated.emit(100, f"Successfully converted to {output_file}")
        except Exception as e:
            self.progress_updated.emit(0, f"Error: {str(e)}")
            raise
        
    def batch_convert(self):
        input_dir = Path(self.input_path)
        output_dir = Path(self.output_path) if self.output_path else input_dir
        
        output_dir.mkdir(parents=True, exist_ok=True)
        rw2_files = list(input_dir.glob('*.RW2')) + list(input_dir.glob('*.rw2'))
        
        if not rw2_files:
            raise ValueError(f"No RW2 files found in {input_dir}")
        
        total_files = len(rw2_files)
        for i, input_file in enumerate(rw2_files):
            if self.cancel_requested:
                break
                
            output_file = output_dir / (input_file.stem + '.exr')
            self.progress_updated.emit(
                int((i+1)/total_files*100),
                f"Converting {i+1}/{total_files}: {input_file.name}"
            )
            self.rw2_to_exr(str(input_file), str(output_file))
            
    def rw2_to_exr(self, input_path, output_path):
        try:
            with rawpy.imread(input_path) as raw:
                rgb = raw.postprocess(
                    gamma=(1,1),
                    no_auto_bright=True,
                    output_bps=16,
                    output_color=rawpy.ColorSpace.raw
                )
            
            rgb_float = rgb.astype(np.float32) / 65535.0
            header = OpenEXR.Header(rgb.shape[1], rgb.shape[0])
            channels = {
                'R': rgb_float[:,:,0].tobytes(),
                'G': rgb_float[:,:,1].tobytes(),
                'B': rgb_float[:,:,2].tobytes()
            }
            
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            exr = OpenEXR.OutputFile(output_path, header)
            exr.writePixels(channels)
            exr.close()
            
        except Exception as e:
            raise Exception(f"Failed to convert {Path(input_path).name}: {str(e)}")


class RW2ToEXRApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RW2 to EXR Converter")
        self.setMinimumSize(300, 500)

        self.conversion_thread = None

        main_widget = QWidget()
        layout = QVBoxLayout()
        
        # Mode selection
        self.mode_group = QGroupBox("Conversion Mode")
        mode_layout = QHBoxLayout()
        self.single_radio = QRadioButton("Single File")
        self.batch_radio = QRadioButton("Batch Directory")
        self.single_radio.setChecked(True)
        mode_layout.addWidget(self.single_radio)
        mode_layout.addWidget(self.batch_radio)
        self.mode_group.setLayout(mode_layout)
        
        # Input selection
        self.input_label = QLabel("Input File/Directory:")
        self.input_path = QLineEdit()
        self.input_path.setPlaceholderText("Select input file or directory")
        self.browse_input = QPushButton("Browse...")
        self.browse_input.clicked.connect(self.select_input)
        
        # Output selection
        self.output_label = QLabel("Output Location:")
        self.output_path = QLineEdit()
        self.output_path.setPlaceholderText("Optional - defaults to same directory")
        self.browse_output = QPushButton("Browse...")
        self.browse_output.clicked.connect(self.select_output)
        
        # Progress
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.status_label = QLabel("Ready")
        self.status_label.setAlignment(Qt.AlignCenter)
        
        # Buttons
        self.convert_btn = QPushButton("Convert")
        self.convert_btn.clicked.connect(self.start_conversion)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.cancel_conversion)
        self.cancel_btn.setEnabled(False)
        
        # Layout
        layout.addWidget(self.mode_group)
        layout.addWidget(self.input_label)
        layout.addWidget(self.input_path)
        layout.addWidget(self.browse_input)
        layout.addWidget(self.output_label)
        layout.addWidget(self.output_path)
        layout.addWidget(self.browse_output)
        layout.addWidget(self.progress)
        layout.addWidget(self.status_label)
        
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.convert_btn)
        button_layout.addWidget(self.cancel_btn)
        layout.addLayout(button_layout)
        
        main_widget.setLayout(layout)
        self.setCentralWidget(main_widget)

    @Slot()
    def select_input(self):
        if self.single_radio.isChecked():
            path, _ = QFileDialog.getOpenFileName(
                self, "Select RAW File", "", "RAW Files (*.RW2 *.rw2)"
            )
        else:
            path = QFileDialog.getExistingDirectory(
                self, "Select Directory with RAW Files"
            )
        
        if path:
            self.input_path.setText(path)

    @Slot()
    def select_output(self):
        if self.single_radio.isChecked():
            path, _ = QFileDialog.getSaveFileName(
                self, "Save EXR File", "", "EXR Files (*.exr)"
            )
        else:
            path = QFileDialog.getExistingDirectory(
                self, "Select Output Directory"
            )
        
        if path:
            self.output_path.setText(path)

    @Slot()
    def start_conversion(self):
        if not self.input_path.text():
            QMessageBox.warning(self, "Warning", "Please select an input file/directory")
            return
            
        self.convert_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.progress.setVisible(True)
        self.progress.setValue(0)
        
        is_batch = self.batch_radio.isChecked()
        self.conversion_thread = ConversionThread(
            self.input_path.text(),
            self.output_path.text(),
            is_batch
        )
        
        self.conversion_thread.progress_updated.connect(self.update_progress)
        self.conversion_thread.conversion_finished.connect(self.conversion_done)
        self.conversion_thread.start()

    def update_progress(self, value, message):
        self.progress.setValue(value)
        self.status_label.setText(message)
        
    def conversion_done(self, success, message):
        self.convert_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        
        if success:
            QMessageBox.information(self, "Success", message)
        else:
            QMessageBox.critical(self, "Error", message)

    @Slot()
    def cancel_conversion(self):
        if self.conversion_thread and self.conversion_thread.isRunning():
            self.conversion_thread.cancel_requested = True
            self.status_label.setText("Cancelling...")
            self.cancel_btn.setEnabled(False)


if __name__ == "__main__":
    app = QApplication(sys.argv)

    window = RW2ToEXRApp()
    window.show()

    app.exec()