"""
Test script for UI components
"""

import sys
import os
from pathlib import Path

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from rich.console import Console
from utils.ui_components import EnhancedUI, ModelBanner, ToolCallTree, TokenTracker

def test_model_banner():
    """Test model banner display"""
    print("\n=== Testing Model Banner ===")
    console = Console()
    
    banner = ModelBanner.create(
        model="GLM-4.7",
        provider="zhipu",
        project_root=PROJECT_ROOT,
        version="v1.0"
    )
    console.print(banner)
    print("✓ Model banner displayed successfully")

def test_tool_tree():
    """Test tool call tree"""
    print("\n=== Testing Tool Call Tree ===")
    console = Console()
    
    tree = ToolCallTree()
    
    # Add some sample tool calls
    tree.add_tool_call("Read", "docs/README.md")
    tree.add_detail("lines", "1-50")
    
    tree.add_tool_call("Grep", "pattern: 'TODO'")
    tree.add_detail("files_matched", "5")
    tree.add_detail("total_matches", "12")
    
    tree.add_tool_call("Write", "output.txt")
    tree.add_detail("bytes_written", "1024")
    
    console.print(tree.get_tree())
    print("✓ Tool call tree displayed successfully")

def test_token_tracker():
    """Test token tracker"""
    print("\n=== Testing Token Tracker ===")
    console = Console()
    
    tracker = TokenTracker()
    tracker.add_usage(1000, 500, "Step 1")
    tracker.add_usage(800, 400, "Step 2")
    tracker.add_usage(1200, 600, "Step 3")
    
    console.print(tracker.get_summary_text())
    console.print()
    console.print(tracker.get_summary())
    print("✓ Token tracker displayed successfully")

def test_enhanced_ui():
    """Test complete enhanced UI"""
    print("\n=== Testing Enhanced UI ===")
    console = Console()
    
    ui = EnhancedUI(
        console=console,
        model="GLM-4.7",
        provider="zhipu",
        project_root=PROJECT_ROOT,
        version="v1.0"
    )
    
    # Show banner
    ui.show_banner()
    
    # Simulate some tool calls
    ui.show_tool_call("LS", {"path": "."})
    ui.show_tool_call("Read", {"path": "README.md", "lines": "1-50"})
    ui.show_tool_call("Grep", {"pattern": "TODO", "path": "**/*.py"})
    
    # Show tool tree
    ui.show_tool_tree()
    
    # Add token usage
    ui.add_token_usage(1000, 500, "Request 1")
    ui.add_token_usage(800, 400, "Request 2")
    
    # Show summary
    ui.show_token_summary()
    
    print("✓ Enhanced UI test completed successfully")

if __name__ == "__main__":
    try:
        test_model_banner()
        test_tool_tree()
        test_token_tracker()
        test_enhanced_ui()
        
        print("\n" + "="*50)
        print("✓ All UI component tests passed!")
        print("="*50)
        
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
