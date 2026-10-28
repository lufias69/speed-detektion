import sys
from PyQt6.QtWidgets import QApplication, QLabel, QPushButton, QVBoxLayout, QWidget


def main():
    app = QApplication(sys.argv)

    window = QWidget()
    window.setWindowTitle("PyQt6 Window Test")
    window.setMinimumSize(300, 150)

    layout = QVBoxLayout(window)
    label = QLabel("If you can see this window, PyQt6 is working.")
    button = QPushButton("Close")
    button.clicked.connect(window.close)
    layout.addWidget(label)
    layout.addWidget(button)

    window.show()
    print("Window should be visible now.")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
