"""
Rule Evaluation Engine

Evaluates signal generation rules from JSON configuration using vectorized
pandas operations. Supports complex multi-condition rules with AND/OR logic.
"""

import logging
import json
from typing import Dict, List, Optional, Any, Union, Callable
from dataclasses import dataclass, field
from enum import Enum

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


class Operator(Enum):
    """Comparison operators for rule conditions."""
    GREATER_THAN = ">"
    LESS_THAN = "<"
    GREATER_EQUAL = ">="
    LESS_EQUAL = "<="
    EQUAL = "=="
    NOT_EQUAL = "!="
    CROSS_ABOVE = "cross_above"  # Value crosses above threshold
    CROSS_BELOW = "cross_below"  # Value crosses below threshold


@dataclass
class Condition:
    """
    Single condition in a rule.
    
    Attributes:
        left: Left operand (column name or value)
        operator: Comparison operator
        right: Right operand (column name or value)
    """
    left: Union[str, float, int]
    operator: str
    right: Union[str, float, int]
    
    def __post_init__(self):
        """Validate and normalize operator."""
        # Map string operators to enum
        op_map = {
            '>': Operator.GREATER_THAN,
            '<': Operator.LESS_THAN,
            '>=': Operator.GREATER_EQUAL,
            '<=': Operator.LESS_EQUAL,
            '==': Operator.EQUAL,
            '!=': Operator.NOT_EQUAL,
            'cross_above': Operator.CROSS_ABOVE,
            'cross_below': Operator.CROSS_BELOW,
        }
        
        if self.operator not in op_map:
            raise ValueError(f"Unknown operator: {self.operator}")
        
        self._operator_enum = op_map[self.operator]
    
    def evaluate(self, df: pd.DataFrame) -> pd.Series:
        """
        Evaluate this condition against a DataFrame.
        
        Args:
            df: DataFrame with indicator columns
            
        Returns:
            Boolean Series indicating where condition is True
        """
        left_val = self._get_value(self.left, df)
        right_val = self._get_value(self.right, df)
        
        op = self._operator_enum
        
        if op == Operator.GREATER_THAN:
            return left_val > right_val
        elif op == Operator.LESS_THAN:
            return left_val < right_val
        elif op == Operator.GREATER_EQUAL:
            return left_val >= right_val
        elif op == Operator.LESS_EQUAL:
            return left_val <= right_val
        elif op == Operator.EQUAL:
            return left_val == right_val
        elif op == Operator.NOT_EQUAL:
            return left_val != right_val
        elif op == Operator.CROSS_ABOVE:
            # Current > threshold AND previous <= threshold
            prev_left = left_val.shift(1)
            return (left_val > right_val) & (prev_left <= right_val)
        elif op == Operator.CROSS_BELOW:
            # Current < threshold AND previous >= threshold
            prev_left = left_val.shift(1)
            return (left_val < right_val) & (prev_left >= right_val)
        
        return pd.Series(False, index=df.index)
    
    def _get_value(
        self,
        operand: Union[str, float, int],
        df: pd.DataFrame
    ) -> Union[pd.Series, float, int]:
        """
        Get the value for an operand.
        
        Args:
            operand: Column name or literal value
            df: DataFrame to look up column names
            
        Returns:
            Series for column references, or literal value
        """
        if isinstance(operand, str):
            # Handle special column references
            if operand.endswith('.prev'):
                base_operand = operand[:-5]
                if not base_operand:
                    raise ValueError("Previous-bar reference is missing a base column name")
                if base_operand in df.columns:
                    return df[base_operand].shift(1)
                raise ValueError(f"Column '{base_operand}' not found for previous-bar reference '{operand}'")

            if operand == 'Close':
                return df['Close']
            elif operand == 'Open':
                return df['Open']
            elif operand == 'High':
                return df['High']
            elif operand == 'Low':
                return df['Low']
            elif operand == 'Volume':
                return df['Volume']
            elif operand in df.columns:
                return df[operand]
            else:
                raise ValueError(f"Column '{operand}' not found in DataFrame")
        
        return operand
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            'left': self.left,
            'operator': self.operator,
            'right': self.right
        }


@dataclass
class Rule:
    """
    Signal generation rule with multiple conditions.
    
    Attributes:
        rule_id: Unique identifier for this rule
        description: Human-readable description
        signal_value: Output signal value (-1, 0, 1)
        conditions: List of conditions (all must be True)
        logic: How to combine conditions ('AND' or 'OR')
    """
    rule_id: str
    description: str
    signal_value: int
    conditions: List[Condition]
    logic: str = "AND"  # 'AND' or 'OR'
    
    def __post_init__(self):
        """Validate signal value."""
        if self.signal_value not in (-1, 0, 1):
            raise ValueError(f"Signal value must be -1, 0, or 1, got {self.signal_value}")
        
        if self.logic not in ('AND', 'OR'):
            raise ValueError(f"Logic must be 'AND' or 'OR', got {self.logic}")
    
    def evaluate(self, df: pd.DataFrame) -> pd.Series:
        """
        Evaluate this rule against a DataFrame.
        
        Args:
            df: DataFrame with indicator columns
            
        Returns:
            Boolean Series indicating where rule is triggered
        """
        if not self.conditions:
            return pd.Series(False, index=df.index)
        
        # Evaluate all conditions
        results = [cond.evaluate(df) for cond in self.conditions]
        
        # Combine based on logic
        if self.logic == 'AND':
            combined = results[0]
            for result in results[1:]:
                combined = combined & result
            return combined
        else:  # OR
            combined = results[0]
            for result in results[1:]:
                combined = combined | result
            return combined
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            'rule_id': self.rule_id,
            'description': self.description,
            'signal_value': self.signal_value,
            'conditions': [c.to_dict() for c in self.conditions],
            'logic': self.logic
        }


class RuleEvaluator:
    """
    Evaluates signal generation rules from JSON configuration.
    
    Parses rule definitions from database and evaluates them against
    price data to generate trading signals.
    
    Example:
        evaluator = RuleEvaluator()
        
        # Add rules from JSON
        rules_json = [
            {
                "rule_id": "LONG_EMA",
                "description": "EMA crossover",
                "signal_value": 1,
                "conditions": [
                    {"left": "EMA_50", "operator": ">", "right": "EMA_200"}
                ]
            }
        ]
        evaluator.add_rules_from_json(rules_json)
        
        # Evaluate
        signals = evaluator.evaluate(df)
    """
    
    def __init__(self):
        """Initialize the rule evaluator."""
        self.rules: List[Rule] = []
        self._rule_map: Dict[str, Rule] = {}
        logger.debug("Initialized RuleEvaluator")
    
    def add_rule(self, rule: Rule) -> None:
        """
        Add a rule to the evaluator.
        
        Args:
            rule: Rule to add
        """
        self.rules.append(rule)
        self._rule_map[rule.rule_id] = rule
        logger.debug(f"Added rule: {rule.rule_id}")
    
    def add_rules_from_json(self, rules_json: List[Dict]) -> None:
        """
        Add multiple rules from JSON (database format).
        
        Args:
            rules_json: List of rule dictionaries
            
        Raises:
            ValueError: If rule format is invalid
        """
        for rule_dict in rules_json:
            try:
                rule = self._parse_rule(rule_dict)
                self.add_rule(rule)
            except Exception as e:
                logger.error(f"Failed to parse rule: {rule_dict}. Error: {e}")
                raise ValueError(f"Invalid rule format: {e}")
        
        logger.info(f"Added {len(rules_json)} rules from JSON")
    
    def _parse_rule(self, rule_dict: Dict) -> Rule:
        """
        Parse a rule dictionary into a Rule object.
        
        Args:
            rule_dict: Rule dictionary from database
            
        Returns:
            Parsed Rule object
        """
        # Parse conditions
        conditions = []
        for cond_dict in rule_dict.get('conditions', []):
            # Handle 'prev' notation for previous values
            left = cond_dict['left']
            if isinstance(left, str) and left.endswith('.prev'):
                # This will be handled during evaluation
                pass
            
            condition = Condition(
                left=left,
                operator=cond_dict['operator'],
                right=cond_dict['right']
            )
            conditions.append(condition)
        
        return Rule(
            rule_id=rule_dict['rule_id'],
            description=rule_dict.get('description', ''),
            signal_value=rule_dict['signal_value'],
            conditions=conditions,
            logic=rule_dict.get('logic', 'AND')
        )
    
    def evaluate(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Evaluate all rules against a DataFrame.
        
        Args:
            df: DataFrame with indicator columns
            
        Returns:
            DataFrame with signal columns for each rule
        """
        if not self.rules:
            logger.warning("No rules to evaluate")
            return pd.DataFrame(index=df.index)
        
        results = {}
        
        for rule in self.rules:
            # Evaluate rule
            triggered = rule.evaluate(df)
            
            # Store signal value where triggered
            signal = pd.Series(0, index=df.index)
            signal[triggered] = rule.signal_value
            
            results[rule.rule_id] = signal
            
            # Count signals
            long_count = (signal == 1).sum()
            short_count = (signal == -1).sum()
            logger.debug(
                f"Rule {rule.rule_id}: {long_count} long, {short_count} short signals"
            )
        
        result_df = pd.DataFrame(results, index=df.index)
        return result_df
    
    def evaluate_consolidated(self, df: pd.DataFrame) -> pd.Series:
        """
        Evaluate all rules and return consolidated signal.
        
        When multiple rules trigger, the signal with highest absolute
        value takes precedence. Conflicting signals (1 and -1) result in 0.
        
        Args:
            df: DataFrame with indicator columns
            
        Returns:
            Series with consolidated signal values
        """
        rule_signals = self.evaluate(df)
        
        if rule_signals.empty:
            return pd.Series(0, index=df.index)
        
        # Sum signals across rules
        consolidated = rule_signals.sum(axis=1)
        
        # Normalize: if conflicting signals, result is 0
        # Otherwise, take the sign
        result = pd.Series(0, index=df.index)
        result[consolidated > 0] = 1
        result[consolidated < 0] = -1
        
        return result
    
    def get_triggered_rules(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Get which rules triggered at each timestamp.
        
        Args:
            df: DataFrame with indicator columns
            
        Returns:
            DataFrame with rule IDs as columns, boolean values
        """
        results = {}
        
        for rule in self.rules:
            triggered = rule.evaluate(df)
            results[rule.rule_id] = triggered
        
        return pd.DataFrame(results, index=df.index)
    
    def get_rule(self, rule_id: str) -> Optional[Rule]:
        """
        Get a rule by ID.
        
        Args:
            rule_id: Rule identifier
            
        Returns:
            Rule if found, None otherwise
        """
        return self._rule_map.get(rule_id)
    
    def clear_rules(self) -> None:
        """Clear all rules."""
        self.rules.clear()
        self._rule_map.clear()
        logger.debug("Cleared all rules")
    
    def validate_against_dataframe(self, df: pd.DataFrame) -> List[str]:
        """
        Validate that all rule references exist in DataFrame.
        
        Args:
            df: DataFrame to validate against
            
        Returns:
            List of validation errors (empty if valid)
        """
        errors = []
        available_cols = set(df.columns)

        def resolve_operand_name(operand: Union[str, float, int]) -> Optional[str]:
            if not isinstance(operand, str):
                return None
            if operand.endswith('.prev'):
                return operand[:-5]
            return operand
        
        for rule in self.rules:
            for condition in rule.conditions:
                # Check left operand
                left_name = resolve_operand_name(condition.left)
                if left_name is not None and left_name not in available_cols:
                    errors.append(
                        f"Rule '{rule.rule_id}': Column '{condition.left}' not found"
                    )
                
                # Check right operand
                right_name = resolve_operand_name(condition.right)
                if right_name is not None and right_name not in available_cols:
                    errors.append(
                        f"Rule '{rule.rule_id}': Column '{condition.right}' not found"
                    )
        
        return errors
