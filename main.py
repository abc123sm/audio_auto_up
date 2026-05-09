from crawler import SouthPlusCrawler
from pcs_manager import PCSDownloader
import time

def main():
    print("=== Starting South Plus Audio Auto Up System ===")
    
    # 1. 执行爬虫抓取并生成清单
    print("\n--- Phase 1: Crawling ---")
    try:
        crawler = SouthPlusCrawler()
        # 抓取前3页以获取最新资源
        crawler.run(start_page=1,num_pages=3)
    except Exception as e:
        print(f"Crawler error: {e}")
    
    # 2. 执行下载编排
    print("\n--- Phase 2: Downloading ---")
    try:
        downloader = PCSDownloader()
        downloader.process_list()
    except Exception as e:
        print(f"Downloader error: {e}")
    
    print("\n=== All tasks completed ===")

if __name__ == "__main__":
    main()
