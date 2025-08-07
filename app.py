import asyncio
import aiohttp
import time
import json
import os
import logging
from datetime import datetime
from typing import Dict, Any
from flask import Flask, jsonify

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
DATA_FILE = "/tmp/urls_data.json"

class UrlMonitor:
    def __init__(self):
        self.urls_intervals = self.load_data()
        self.lock = asyncio.Lock()
        self.session = None
        logger.info("Monitor inicializado con URLs: %s", self.urls_intervals)

    def load_data(self):
        try:
            if os.path.exists(DATA_FILE):
                with open(DATA_FILE) as f:
                    return json.load(f)
        except Exception as e:
            logger.error("Error cargando datos: %s", e)
        return {}

    def save_data(self):
        try:
            with open(DATA_FILE, 'w') as f:
                json.dump(self.urls_intervals, f)
        except Exception as e:
            logger.error("Error guardando datos: %s", e)

    async def init_session(self):
        if not self.session:
            self.session = aiohttp.ClientSession()

    async def fetch_url(self, url: str):
        try:
            await self.init_session()
            start = time.time()
            async with self.session.get(url) as response:
                elapsed = time.time() - start
                logger.info("%s - Status: %s - Tiempo: %.2fs", url, response.status, elapsed)
                return await response.text()
        except Exception as e:
            logger.error("Error en %s: %s", url, str(e))
            return None

    async def monitor_urls(self):
        await self.init_session()
        logger.info("Iniciando monitor de URLs...")
        while True:
            tasks = []
            async with self.lock:
                for url, data in self.urls_intervals.items():
                    if time.time() - data['last_check'] >= data['interval']:
                        tasks.append(self.fetch_url(url))
                        data['last_check'] = time.time()
            
            if tasks:
                await asyncio.gather(*tasks)
                self.save_data()
            
            await asyncio.sleep(5)

    async def update_urls_list(self):
        await self.init_session()
        logger.info("Iniciando actualización periódica de URLs...")
        while True:
            try:
                async with self.session.get("https://timercrud-w93p.onrender.com/links") as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info("Actualizando lista de URLs desde API")
                        
                        async with self.lock:
                            current = set(self.urls_intervals.keys())
                            nuevos = set(item['link'] for item in data)
                            
                            for item in data:
                                url = item['link']
                                interval = int(item['time'])
                                if url not in self.urls_intervals:
                                    logger.info("Añadido: %s (cada %ss)", url, interval)
                                    self.urls_intervals[url] = {'interval': interval, 'last_check': 0}
                            
                            for url in current - nuevos:
                                logger.info("Eliminado: %s", url)
                                del self.urls_intervals[url]
                            self.save_data()
            except Exception as e:
                logger.error("Error actualizando URLs: %s", str(e))
            
            await asyncio.sleep(300)

@app.route('/ping')
def ping():
    logger.info("Ping recibido")
    return jsonify({"status": "active", "timestamp": datetime.now().isoformat()})

async def run_monitor():
    monitor = UrlMonitor()
    await asyncio.gather(
        monitor.update_urls_list(),
        monitor.monitor_urls()
    )

def start_async():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run_monitor())

if __name__ == "__main__":
    import threading
    threading.Thread(target=start_async, daemon=True).start()
    
    from waitress import serve
    port = int(os.environ.get("PORT", 10000))  # Usar el puerto de Render
    logger.info("Iniciando servidor en puerto %s", port)
    serve(app, host="0.0.0.0", port=port)
