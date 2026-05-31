import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

import uvicorn
from config import PORT

if __name__ == "__main__":
    uvicorn.run("webapp.routes:app", host="0.0.0.0", port=PORT)
