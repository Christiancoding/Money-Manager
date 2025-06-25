#!/usr/bin/env python3
"""
Asset Download Utility

A comprehensive tool for downloading and managing Bootstrap and Font Awesome
assets for local hosting in Flask applications. Ensures proper file structure,
path corrections, and integrity validation.
"""

import sys
import os
import logging
import requests
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import hashlib
import re

# Ensure Python 3 compatibility
if sys.version_info < (3, 7):
    print("This script requires Python 3.7+. Please upgrade.")
    sys.exit(1)


class AssetDownloader:
    """Advanced asset download and management utility for web frameworks."""
    
    def __init__(self, base_path: str = "static"):
        """Initialize asset downloader with configurable base path."""
        self.base_path = Path(base_path)
        self._setup_logging()
        self._setup_directories()
        self._define_assets()
    
    def _setup_logging(self) -> None:
        """Configure comprehensive logging infrastructure."""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s: %(message)s',
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler('asset_download.log')
            ]
        )
        self.logger = logging.getLogger(__name__)
        self.logger.info("Asset downloader initialized")
    
    def _setup_directories(self) -> None:
        """Create required directory structure with proper error handling."""
        directories = ['css', 'js', 'webfonts']
        
        for directory in directories:
            dir_path = self.base_path / directory
            try:
                dir_path.mkdir(parents=True, exist_ok=True)
                self.logger.debug(f"Directory ready: {dir_path}")
            except PermissionError:
                self.logger.error(f"Permission denied creating directory: {dir_path}")
                raise
            except Exception as e:
                self.logger.error(f"Failed to create directory {dir_path}: {e}")
                raise
    
    def _define_assets(self) -> None:
        """Define comprehensive asset configuration with validation."""
        self.assets: Dict[str, Dict[str, Any]] = {
            'bootstrap_css': {
                'url': 'https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css',
                'path': 'css/bootstrap.min.css',
                'description': 'Bootstrap CSS Framework',
                'required': True
            },
            'bootstrap_js': {
                'url': 'https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js',
                'path': 'js/bootstrap.bundle.min.js',
                'description': 'Bootstrap JavaScript Bundle',
                'required': True
            },
            'fontawesome_css': {
                'url': 'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css',
                'path': 'css/fontawesome.min.css',
                'description': 'Font Awesome CSS',
                'required': True,
                'post_process': True
            }
        }
        
        # Font Awesome webfont files
        font_formats = ['woff2', 'woff']
        font_types = ['solid-900', 'regular-400', 'brands-400']
        
        for font_type in font_types:
            for format_type in font_formats:
                key = f'fa_{font_type.replace("-", "_")}_{format_type}'
                self.assets[key] = {
                    'url': f'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/webfonts/fa-{font_type}.{format_type}',
                    'path': f'webfonts/fa-{font_type}.{format_type}',
                    'description': f'Font Awesome {font_type} ({format_type})',
                    'required': False
                }
    
    def download_file(self, url: str, local_path: Path, timeout: int = 30) -> Tuple[bool, Optional[str]]:
        """
        Download file with comprehensive error handling and validation.
        
        Args:
            url: Source URL for download
            local_path: Local destination path
            timeout: Request timeout in seconds
            
        Returns:
            Tuple of (success_status, error_message)
        """
        try:
            self.logger.info(f"Downloading: {url}")
            
            response = requests.get(url, timeout=timeout, stream=True)
            response.raise_for_status()
            
            # Validate content type for known file types
            content_type = response.headers.get('content-type', '').lower()
            if local_path.suffix == '.css' and 'text/css' not in content_type:
                self.logger.warning(f"Unexpected content type for CSS: {content_type}")
            
            # Write file with progress indication
            downloaded_size = 0
            
            with open(local_path, 'wb') as file:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        file.write(chunk)
                        downloaded_size += len(chunk)
            
            # Verify file was written successfully
            if not local_path.exists() or local_path.stat().st_size == 0:
                return False, "File was not written properly"
            
            self.logger.info(f"Successfully downloaded: {local_path} ({downloaded_size:,} bytes)")
            return True, None
            
        except requests.exceptions.Timeout:
            error_msg = f"Download timeout after {timeout}s"
            self.logger.error(f"{error_msg}: {url}")
            return False, error_msg
            
        except requests.exceptions.RequestException as e:
            error_msg = f"Network error: {str(e)}"
            self.logger.error(f"{error_msg}: {url}")
            return False, error_msg
            
        except PermissionError:
            error_msg = f"Permission denied writing to: {local_path}"
            self.logger.error(error_msg)
            return False, error_msg
            
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            self.logger.error(f"{error_msg} while downloading: {url}")
            return False, error_msg
    
    def fix_fontawesome_paths(self, css_path: Path) -> bool:
        """
        Fix Font Awesome CSS font paths for local Flask hosting.
        
        Args:
            css_path: Path to Font Awesome CSS file
            
        Returns:
            Success status of path correction
        """
        try:
            self.logger.info(f"Processing Font Awesome CSS: {css_path}")
            
            with open(css_path, 'r', encoding='utf-8') as file:
                content = file.read()
            
            # Replace CDN font paths with local static paths
            original_content = content
            content = re.sub(
                r'\.\.\/webfonts\/',
                '/static/webfonts/',
                content
            )
            
            # Also handle any absolute CDN URLs that might exist
            content = re.sub(
                r'https://cdnjs\.cloudflare\.com/ajax/libs/font-awesome/[^/]+/webfonts/',
                '/static/webfonts/',
                content
            )
            
            if content != original_content:
                with open(css_path, 'w', encoding='utf-8') as file:
                    file.write(content)
                self.logger.info(f"Fixed font paths in: {css_path}")
                return True
            else:
                self.logger.info("No font path corrections needed")
                return True
                
        except Exception as e:
            self.logger.error(f"Failed to fix font paths in {css_path}: {e}")
            return False
    
    def validate_downloads(self) -> dict[str, bool]:
        """
        Validate all downloaded files exist and have reasonable sizes.
        
        Returns:
            Dictionary mapping asset keys to validation status
        """
        validation_results: dict[str, bool] = {}
        
        for asset_key, asset_info in self.assets.items():
            file_path = self.base_path / asset_info['path']
            file_path: Path  # type annotation for static analysis
            
            if not file_path.exists():
                validation_results[asset_key] = False
                self.logger.warning(f"Missing file: {file_path}")
                continue
            
            file_size = file_path.stat().st_size
            if file_size < 100:  # Suspiciously small files
                validation_results[asset_key] = False
                self.logger.warning(f"Suspiciously small file: {file_path} ({file_size} bytes)")
                continue
            
            validation_results[asset_key] = True
            self.logger.debug(f"Validated: {file_path} ({file_size:,} bytes)")
        
        return validation_results
    
    def download_all_assets(self) -> Dict[str, str]:
        """
        Download all defined assets with comprehensive error tracking.
        
        Returns:
            Dictionary mapping asset keys to status messages
        """
        results: Dict[str, str] = {}
        successful_downloads = 0
        total_assets = len(self.assets)
        
        self.logger.info(f"Starting download of {total_assets} assets...")
        
        for asset_key, asset_info in self.assets.items():
            asset_info: Dict[str, Any]  # type hint for clarity
            local_path = self.base_path / asset_info['path']
            
            # Skip if file already exists and is valid
            if local_path.exists() and local_path.stat().st_size > 100:
                self.logger.info(f"Skipping existing file: {local_path}")
                results[asset_key] = "Already exists"
                successful_downloads += 1
                continue
            
            success, error_message = self.download_file(asset_info['url'], local_path)
            
            if success:
                results[asset_key] = "Downloaded successfully"
                successful_downloads += 1
                
                # Apply post-processing if required
                if asset_info.get('post_process') and asset_key == 'fontawesome_css':
                    if self.fix_fontawesome_paths(local_path):
                        results[asset_key] += " (paths corrected)"
                    else:
                        results[asset_key] += " (path correction failed)"
            else:
                results[asset_key] = f"Failed: {error_message}"
                if asset_info.get('required', False):
                    self.logger.error(f"Required asset failed: {asset_key}")
        
        # Validation pass
        self.logger.info("Performing validation checks...")
        validation_results = self.validate_downloads()
        validated_count = sum(validation_results.values())
        
        # Summary reporting
        self.logger.info(f"Download Summary: {successful_downloads}/{total_assets} downloaded")
        self.logger.info(f"Validation Summary: {validated_count}/{total_assets} validated")
        
        if successful_downloads == total_assets and validated_count == total_assets:
            self.logger.info("🎉 All assets downloaded and validated successfully!")
        elif successful_downloads < total_assets:
            self.logger.warning(f"⚠️  {total_assets - successful_downloads} assets failed to download")
        
        return results
    
    def cleanup_failed_downloads(self) -> int:
        """
        Remove any files that failed validation or are corrupted.
        
        Returns:
            Number of files cleaned up
        """
        cleaned_count = 0
        validation_results = self.validate_downloads()
        
        for asset_key, is_valid in validation_results.items():
            if not is_valid:
                file_path = self.base_path / self.assets[asset_key]['path']
                if file_path.exists():
                    try:
                        file_path.unlink()
                        self.logger.info(f"Cleaned up invalid file: {file_path}")
                        cleaned_count += 1
                    except Exception as e:
                        self.logger.error(f"Failed to clean up {file_path}: {e}")
        
        return cleaned_count


def main():
    """Primary execution entry point with comprehensive error management."""
    try:
        downloader = AssetDownloader()
        
        print("🚀 Starting asset download process...")
        print("=" * 50)
        
        results = downloader.download_all_assets()
        
        print("\n📋 Download Results:")
        print("-" * 30)
        for asset_key, status in results.items():
            asset_name = downloader.assets[asset_key]['description']
            status_emoji = "✅" if "success" in status.lower() or "exists" in status.lower() else "❌"
            print(f"{status_emoji} {asset_name}: {status}")
        
        # Cleanup any failed downloads
        cleaned_count = downloader.cleanup_failed_downloads()
        if cleaned_count > 0:
            print(f"\n🧹 Cleaned up {cleaned_count} invalid files")
        
        print(f"\n📁 Assets saved to: {downloader.base_path.absolute()}")
        print("\n🔧 Next steps:")
        print("1. Update your base.html template to use local assets")
        print("2. Ensure Flask static folder is configured properly")
        print("3. Test your application to verify icons display correctly")
        
    except KeyboardInterrupt:
        print("\n⏹️  Download cancelled by user")
        sys.exit(0)
    except Exception as e:
        logging.error(f"Unhandled exception: {e}", exc_info=True)
        print(f"\n❌ Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()