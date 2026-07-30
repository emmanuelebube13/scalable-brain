"""
Indicator Dependency Graph

Builds and manages the dependency relationships between indicators,
enabling lazy evaluation where only required indicators are calculated.
"""

import logging
from typing import Dict, List, Set, Optional, Any
from dataclasses import dataclass, field
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class IndicatorNode:
    """
    Node in the dependency graph representing an indicator instance.
    
    Attributes:
        instance_name: Unique name for this indicator instance (e.g., 'EMA_50')
        indicator_key: Base indicator type (e.g., 'EMA')
        params: Parameters for this instance
        output_column: Specific output to use
        dependencies: Other indicator nodes this depends on
    """
    instance_name: str
    indicator_key: str
    params: Dict[str, Any] = field(default_factory=dict)
    output_column: Optional[str] = None
    dependencies: Set[str] = field(default_factory=set)
    
    def __hash__(self):
        return hash(self.instance_name)
    
    def __eq__(self, other):
        if isinstance(other, IndicatorNode):
            return self.instance_name == other.instance_name
        return False


class DependencyGraph:
    """
    Manages indicator dependencies to enable efficient lazy evaluation.
    
    Tracks which indicators are needed for each strategy and builds
    an execution order that respects dependencies.
    
    Example:
        graph = DependencyGraph()
        graph.add_indicator('EMA_50', 'EMA', {'window': 50})
        graph.add_indicator('EMA_200', 'EMA', {'window': 200})
        graph.add_indicator('ADX_14', 'ADX', {'window': 14})
        
        order = graph.get_execution_order()
        # Returns: ['EMA_50', 'EMA_200', 'ADX_14']
    """
    
    def __init__(self):
        """Initialize empty dependency graph."""
        self._nodes: Dict[str, IndicatorNode] = {}
        self._dependents: Dict[str, Set[str]] = defaultdict(set)
        logger.debug("Initialized DependencyGraph")
    
    def add_indicator(
        self,
        instance_name: str,
        indicator_key: str,
        params: Optional[Dict[str, Any]] = None,
        output_column: Optional[str] = None,
        dependencies: Optional[List[str]] = None
    ) -> IndicatorNode:
        """
        Add an indicator to the dependency graph.
        
        Args:
            instance_name: Unique name for this instance
            indicator_key: Base indicator type
            params: Parameters for calculation
            output_column: Specific output column
            dependencies: List of other instance names this depends on
            
        Returns:
            The created IndicatorNode
        """
        node = IndicatorNode(
            instance_name=instance_name,
            indicator_key=indicator_key,
            params=params or {},
            output_column=output_column,
            dependencies=set(dependencies or [])
        )
        
        self._nodes[instance_name] = node
        
        # Track reverse dependencies
        for dep in node.dependencies:
            self._dependents[dep].add(instance_name)
        
        logger.debug(f"Added indicator node: {instance_name} ({indicator_key})")
        return node
    
    def get_node(self, instance_name: str) -> Optional[IndicatorNode]:
        """
        Get an indicator node by name.
        
        Args:
            instance_name: Name of the indicator instance
            
        Returns:
            IndicatorNode if found, None otherwise
        """
        return self._nodes.get(instance_name)
    
    def get_dependencies(self, instance_name: str) -> Set[str]:
        """
        Get direct dependencies for an indicator.
        
        Args:
            instance_name: Name of the indicator instance
            
        Returns:
            Set of dependency instance names
        """
        node = self._nodes.get(instance_name)
        if node:
            return node.dependencies
        return set()
    
    def get_all_dependencies(self, instance_name: str) -> Set[str]:
        """
        Get all transitive dependencies for an indicator.
        
        Args:
            instance_name: Name of the indicator instance
            
        Returns:
            Set of all dependency instance names (direct and indirect)
        """
        all_deps = set()
        to_process = [instance_name]
        visited = set()
        
        while to_process:
            current = to_process.pop()
            if current in visited:
                continue
            visited.add(current)
            
            node = self._nodes.get(current)
            if node:
                for dep in node.dependencies:
                    all_deps.add(dep)
                    to_process.append(dep)
        
        return all_deps
    
    def get_execution_order(self) -> List[str]:
        """
        Get topologically sorted execution order for all indicators.
        
        Uses Kahn's algorithm for topological sorting, ensuring that
        indicators are calculated after their dependencies.
        
        Returns:
            List of indicator instance names in execution order
            
        Raises:
            ValueError: If circular dependencies are detected
        """
        # Build in-degree map
        in_degree = {name: len(node.dependencies) for name, node in self._nodes.items()}
        
        # Start with nodes that have no dependencies
        queue = [name for name, degree in in_degree.items() if degree == 0]
        result = []
        
        while queue:
            # Process nodes with no remaining dependencies
            current = queue.pop(0)
            result.append(current)
            
            # Reduce in-degree for dependents
            for dependent in self._dependents.get(current, set()):
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)
        
        # Check for circular dependencies
        if len(result) != len(self._nodes):
            remaining = set(self._nodes.keys()) - set(result)
            raise ValueError(f"Circular dependency detected in indicators: {remaining}")
        
        logger.debug(f"Execution order: {result}")
        return result
    
    def get_required_indicators(self, required_outputs: List[str]) -> Set[str]:
        """
        Get the minimal set of indicators needed to produce given outputs.
        
        This enables lazy evaluation - only calculate indicators that are
        actually needed for the current strategy.
        
        Args:
            required_outputs: List of required indicator instance names
            
        Returns:
            Set of all indicator instances needed (including dependencies)
        """
        required = set()
        to_process = list(required_outputs)
        
        while to_process:
            current = to_process.pop()
            if current in required:
                continue
            
            required.add(current)
            
            # Add dependencies
            node = self._nodes.get(current)
            if node:
                for dep in node.dependencies:
                    if dep not in required:
                        to_process.append(dep)
        
        logger.debug(f"Required indicators for {required_outputs}: {required}")
        return required
    
    def merge(self, other: 'DependencyGraph') -> 'DependencyGraph':
        """
        Merge another dependency graph into this one.
        
        Args:
            other: Another DependencyGraph to merge
            
        Returns:
            Self for method chaining
        """
        for name, node in other._nodes.items():
            if name not in self._nodes:
                self.add_indicator(
                    instance_name=node.instance_name,
                    indicator_key=node.indicator_key,
                    params=node.params,
                    output_column=node.output_column,
                    dependencies=list(node.dependencies)
                )
        
        logger.debug(f"Merged dependency graph, now has {len(self._nodes)} nodes")
        return self
    
    def clear(self) -> None:
        """Clear all nodes from the graph."""
        self._nodes.clear()
        self._dependents.clear()
        logger.debug("Cleared dependency graph")
    
    def __len__(self) -> int:
        """Return number of indicator nodes."""
        return len(self._nodes)
    
    def __contains__(self, instance_name: str) -> bool:
        """Check if an indicator instance exists in the graph."""
        return instance_name in self._nodes
