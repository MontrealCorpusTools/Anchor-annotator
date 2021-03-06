import sys
import warnings
from anchor.main import MainWindow, Application

def run_anchor():  # pragma: no cover
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        app = Application(sys.argv)
        main = MainWindow()

        app.setActiveWindow(main)
        main.show()
        sys.exit(app.exec_())

if __name__ == '__main__':
    run_anchor()