# models/analysis_config.py
import json
import logging
import os
from utils.config_path_manager import ConfigPathManager  # Import the new class
from utils.defaults import default_latency_metrics, default_total_time_metrics

class AnalysisMetricsConfig:
    """
    Configuration class for custom analysis metrics.
    Manages definitions of latency metrics and total time metrics.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Initialize config path manager
        self._config_path_manager = ConfigPathManager()
        
        # Single source of truth for the bundled defaults (see ``defaults``).
        self._latency_metrics = default_latency_metrics()
        self._total_time_metrics = default_total_time_metrics()

        # Try to load from default configuration file if it exists
        self._try_load_default_config()
    
    def _try_load_default_config(self):
        """
        Try to load configuration from the default config file.
        Uses the ConfigPathManager to locate the default metrics configuration.
        """
        try:
            # Get path to default metrics configuration
            config_path = self._config_path_manager.get_metrics_config_path("default_metrics.json")
            
            if config_path and os.path.exists(config_path):
                self.logger.info(f"Found default metrics configuration: {config_path}")
                if self.load_from_json(config_path):
                    self.logger.info(f"Loaded default metrics configuration from {config_path}")
                    return
                else:
                    self.logger.warning(f"Failed to load default metrics configuration from {config_path}")
            else:
                self.logger.info("Default metrics configuration not found")
                
                # Ensure default config exists for next time
                self._config_path_manager.ensure_default_configs()
        except Exception as e:
            self.logger.warning(f"Error loading default metrics configuration: {str(e)}")
        
        self.logger.info("Using built-in defaults for metrics configuration")
    
    def get_latency_metrics(self):
        """
        Get all configured latency metrics.
        
        Returns:
            list: List of latency metric configurations
        """
        return self._latency_metrics.copy()
    
    def get_enabled_latency_metrics(self):
        """
        Get only enabled latency metrics.
        
        Returns:
            list: List of enabled latency metric configurations
        """
        return [metric for metric in self._latency_metrics if metric.get("enabled", True)]
    
    def get_total_time_metrics(self):
        """
        Get all configured total time metrics.
        
        Returns:
            list: List of total time metric configurations
        """
        return self._total_time_metrics.copy()
    
    def get_enabled_total_time_metrics(self):
        """
        Get only enabled total time metrics.
        
        Returns:
            list: List of enabled total time metric configurations
        """
        return [metric for metric in self._total_time_metrics if metric.get("enabled", True)]
    
    def add_latency_metric(self, name, behavior, enabled=True):
        """
        Add a new latency metric.
        
        Args:
            name (str): Name of the metric
            behavior (str): Behavior to measure latency for
            enabled (bool, optional): Whether the metric is enabled
            
        Returns:
            bool: True if added successfully, False if name already exists
        """
        # Check if metric with this name already exists
        if any(metric["name"] == name for metric in self._latency_metrics):
            self.logger.warning(f"Latency metric with name '{name}' already exists")
            return False
        
        # Add new metric
        self._latency_metrics.append({
            "name": name,
            "behavior": behavior,
            "enabled": enabled
        })
        
        self.logger.info(f"Added latency metric: {name} for behavior '{behavior}'")
        return True
    
    def add_total_time_metric(self, name, behaviors, enabled=True):
        """
        Add a new total time metric.
        
        Args:
            name (str): Name of the metric
            behaviors (list): List of behaviors to include
            enabled (bool, optional): Whether the metric is enabled
            
        Returns:
            bool: True if added successfully, False if name already exists
        """
        # Check if metric with this name already exists
        if any(metric["name"] == name for metric in self._total_time_metrics):
            self.logger.warning(f"Total time metric with name '{name}' already exists")
            return False
        
        # Add new metric
        self._total_time_metrics.append({
            "name": name,
            "behaviors": behaviors.copy(),
            "enabled": enabled
        })
        
        self.logger.info(f"Added total time metric: {name} for behaviors {behaviors}")
        return True
    
    def update_latency_metric(self, old_name, new_name, behavior, enabled):
        """
        Update an existing latency metric.
        
        Args:
            old_name (str): Current name of the metric
            new_name (str): New name for the metric
            behavior (str): Behavior to measure latency for
            enabled (bool): Whether the metric is enabled
            
        Returns:
            bool: True if updated successfully, False if not found or name conflict
        """
        # Find the metric to update
        for i, metric in enumerate(self._latency_metrics):
            if metric["name"] == old_name:
                # Check for name conflict if name is changing
                if old_name != new_name and any(m["name"] == new_name for m in self._latency_metrics):
                    self.logger.warning(f"Cannot update latency metric: name '{new_name}' already exists")
                    return False
                
                # Update the metric
                self._latency_metrics[i] = {
                    "name": new_name,
                    "behavior": behavior,
                    "enabled": enabled
                }
                
                self.logger.info(f"Updated latency metric: {old_name} -> {new_name}")
                return True
        
        self.logger.warning(f"Latency metric '{old_name}' not found for update")
        return False
    
    def update_total_time_metric(self, old_name, new_name, behaviors, enabled):
        """
        Update an existing total time metric.
        
        Args:
            old_name (str): Current name of the metric
            new_name (str): New name for the metric
            behaviors (list): List of behaviors to include
            enabled (bool): Whether the metric is enabled
            
        Returns:
            bool: True if updated successfully, False if not found or name conflict
        """
        # Find the metric to update
        for i, metric in enumerate(self._total_time_metrics):
            if metric["name"] == old_name:
                # Check for name conflict if name is changing
                if old_name != new_name and any(m["name"] == new_name for m in self._total_time_metrics):
                    self.logger.warning(f"Cannot update total time metric: name '{new_name}' already exists")
                    return False
                
                # Update the metric
                self._total_time_metrics[i] = {
                    "name": new_name,
                    "behaviors": behaviors.copy(),
                    "enabled": enabled
                }
                
                self.logger.info(f"Updated total time metric: {old_name} -> {new_name}")
                return True
        
        self.logger.warning(f"Total time metric '{old_name}' not found for update")
        return False
    
    def remove_latency_metric(self, name):
        """
        Remove a latency metric.
        
        Args:
            name (str): Name of the metric to remove
            
        Returns:
            bool: True if removed successfully, False if not found or is built-in
        """
        # Don't allow removing default Attack Latency
        if name == "Attack Latency" and len(self._latency_metrics) == 1:
            self.logger.warning("Cannot remove default Attack Latency metric")
            return False
        
        # Find and remove the metric
        for i, metric in enumerate(self._latency_metrics):
            if metric["name"] == name:
                del self._latency_metrics[i]
                self.logger.info(f"Removed latency metric: {name}")
                return True
        
        self.logger.warning(f"Latency metric '{name}' not found for removal")
        return False
    
    @staticmethod
    def _metric_slug(name):
        """Normalised key used to store a metric's result.

        Mirrors the slug ``analysis_model`` derives
        (``name.lower().replace(' ', '_')``) but also strips surrounding
        whitespace, so "Total Aggression" and "total aggression " collide.
        """
        return str(name).strip().lower().replace(" ", "_")

    def find_slug_collisions(self, latency_metrics=None, total_time_metrics=None):
        """Return [(first_name, colliding_name), ...] across BOTH categories.

        A latency metric and a total-time metric that normalise to the same
        slug would overwrite each other's value in the analysis results dict
        (BUG-013), so collisions are detected across the union, not per-list.
        """
        latency = self._latency_metrics if latency_metrics is None else latency_metrics
        total = self._total_time_metrics if total_time_metrics is None else total_time_metrics

        seen = {}
        collisions = []
        for metric in list(latency or []) + list(total or []):
            name = metric.get("name", "")
            slug = self._metric_slug(name)
            if not slug:
                continue
            if slug in seen:
                collisions.append((seen[slug], name))
            else:
                seen[slug] = name
        return collisions

    def replace_metrics(self, latency_metrics, total_time_metrics):
        """
        Atomically replace both metric lists.

        Convenience API for UI dialogs that build a fresh set of metrics
        rather than editing them entry-by-entry. The previous workflow had
        callers reach into ``_latency_metrics`` / ``_total_time_metrics``
        directly, which bypassed validation; this method centralises the
        assignment AND enforces the cross-category slug-uniqueness invariant
        in one place (BUG-013).

        Args:
            latency_metrics (list[dict]): New latency-metric entries.
            total_time_metrics (list[dict]): New total-time-metric entries.

        Raises:
            ValueError: if two metrics (in either category) normalise to the
                same result slug.
        """
        collisions = self.find_slug_collisions(latency_metrics, total_time_metrics)
        if collisions:
            detail = "; ".join(f"'{a}' / '{b}'" for a, b in collisions)
            raise ValueError(
                "Metric names collide after normalisation (case- and "
                f"space-insensitive): {detail}. Please give each metric a "
                "distinct name across latency and total-time."
            )

        self._latency_metrics = [dict(m) for m in (latency_metrics or [])]
        self._total_time_metrics = [dict(m) for m in (total_time_metrics or [])]
        self.logger.info(
            f"Replaced metrics configuration: "
            f"{len(self._latency_metrics)} latency, "
            f"{len(self._total_time_metrics)} total-time"
        )

    def remove_total_time_metric(self, name):
        """
        Remove a total time metric.
        
        Args:
            name (str): Name of the metric to remove
            
        Returns:
            bool: True if removed successfully, False if not found or is built-in
        """
        # Don't allow removing both default metrics
        default_metrics = ["Total Aggression", "Total Aggression(without tail-rattles)"]
        if name in default_metrics and len(self._total_time_metrics) <= 2:
            remaining = [m for m in self._total_time_metrics if m["name"] != name]
            if len(remaining) < 1 or all(m["name"] in default_metrics for m in remaining):
                self.logger.warning(f"Cannot remove default metric '{name}' - at least one default must remain")
                return False
        
        # Find and remove the metric
        for i, metric in enumerate(self._total_time_metrics):
            if metric["name"] == name:
                del self._total_time_metrics[i]
                self.logger.info(f"Removed total time metric: {name}")
                return True
        
        self.logger.warning(f"Total time metric '{name}' not found for removal")
        return False
    
    def to_dict(self):
        """
        Convert configuration to dictionary for serialization.
        
        Returns:
            dict: Configuration as dictionary
        """
        return {
            "latency_metrics": self._latency_metrics,
            "total_time_metrics": self._total_time_metrics
        }
    
    def from_dict(self, config_dict):
        """
        Load configuration from dictionary.
        
        Args:
            config_dict (dict): Configuration dictionary
            
        Returns:
            bool: True if loaded successfully, False otherwise
        """
        try:
            if "latency_metrics" in config_dict:
                self._latency_metrics = config_dict["latency_metrics"]
            
            if "total_time_metrics" in config_dict:
                self._total_time_metrics = config_dict["total_time_metrics"]
            
            return True
        except Exception as e:
            self.logger.error(f"Error loading metrics configuration: {str(e)}")
            return False
    
    def save_to_file(self, file_path):
        """
        Save configuration to a JSON file.
        
        Args:
            file_path (str): Path to save configuration
            
        Returns:
            bool: True if saved successfully, False otherwise
        """
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            # Convert to dictionary and save
            config_dict = self.to_dict()
            with open(file_path, 'w') as f:
                json.dump(config_dict, f, indent=2)
            
            self.logger.info(f"Saved metrics configuration to {file_path}")
            return True
        except Exception as e:
            self.logger.error(f"Error saving metrics configuration: {str(e)}")
            return False
    
    def load_from_file(self, file_path):
        """
        Load configuration from a JSON file.
        
        Args:
            file_path (str): Path to load configuration from
            
        Returns:
            bool: True if loaded successfully, False otherwise
        """
        try:
            if not os.path.exists(file_path):
                self.logger.warning(f"Configuration file not found: {file_path}")
                return False
            
            # Load from file
            with open(file_path, 'r') as f:
                config_dict = json.load(f)
            
            # Apply configuration
            result = self.from_dict(config_dict)
            if result:
                self.logger.info(f"Loaded metrics configuration from {file_path}")
            
            return result
        except Exception as e:
            self.logger.error(f"Error loading metrics configuration: {str(e)}")
            return False
    
    def save_to_json(self, file_path):
        """
        Save configuration to a JSON file.
        Alias for save_to_file for compatibility.
        
        Args:
            file_path (str): Path to save configuration
            
        Returns:
            bool: True if saved successfully, False otherwise
        """
        return self.save_to_file(file_path)
    
    def load_from_json(self, file_path):
        """
        Load configuration from a JSON file.
        Alias for load_from_file for compatibility.
        
        Args:
            file_path (str): Path to load configuration from
            
        Returns:
            bool: True if loaded successfully, False otherwise
        """
        return self.load_from_file(file_path)
    
    def reset_to_defaults(self):
        """
        Reset configuration to default values.

        Returns:
            bool: Always returns True
        """
        # Re-initialise from the single source of truth.
        self._latency_metrics = default_latency_metrics()
        self._total_time_metrics = default_total_time_metrics()

        self.logger.info("Reset metrics configuration to defaults")
        return True