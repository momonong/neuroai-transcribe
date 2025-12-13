"""
Comprehensive test suite for Clinical Agent
Tests multiple ASD diagnostic scenarios
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_module import ClinicalAgent, process_and_validate
from config import LLAMA_MODEL_PATH
import json


class TestScenarios:
    """Collection of clinical test scenarios"""
    
    @staticmethod
    def lion_scenario():
        """Classic Lion/獅子 scenario - tests basic contextual restoration"""
        return {
            "name": "Lion Scenario",
            "context": "醫師手持玩具獅子，發出吼叫聲以吸引兒童注意",
            "transcript": """[00:15] 醫師: "看，這個是什麼？大大的，吼～是獅子！"
[00:20] 兒童: "Shi... shi... uh..."
[00:22] 醫師: "對！獅子！你說『獅子』"
[00:25] 兒童: "O... zi..."
""",
            "expected_keywords": ["獅子", "獅", "醫師", "兒童"]
        }
    
    @staticmethod
    def bus_scenario():
        """Bus scenario - tests object recognition with repetition"""
        return {
            "name": "Bus Scenario",
            "context": "醫師展示玩具巴士，測試兒童的物品命名能力",
            "transcript": """[00:30] 醫師: "這是什麼車？紅色的，很大台，是公車！"
[00:35] 兒童: "Ba... ba... bus..."
[00:38] 醫師: "對，公車！中文叫『公車』"
[00:42] 兒童: "Gong... che..."
""",
            "expected_keywords": ["公車", "巴士", "醫師", "兒童"]
        }
    
    @staticmethod
    def eye_contact_scenario():
        """Eye contact assessment - tests social interaction observation"""
        return {
            "name": "Eye Contact Assessment",
            "context": "醫師評估兒童的眼神接觸能力",
            "transcript": """[01:00] 醫師: "小朋友，看這裡，看醫師的眼睛"
[01:05] 家長: "他比較少眼神接觸，通常都看地板"
[01:10] 兒童: "火車... 火車..."
[01:12] 醫師: "我注意到他對旋轉的物體特別有興趣"
""",
            "expected_keywords": ["醫師", "家長", "兒童", "眼神", "火車"]
        }


def run_test_suite():
    """Execute all test scenarios"""
    print("=" * 70)
    print("NCKU Clinical ASR Agent - Comprehensive Test Suite")
    print("=" * 70)
    
    # Initialize Agent once
    print("\n🔄 Initializing Clinical Agent...")
    agent = ClinicalAgent(model_path=LLAMA_MODEL_PATH)
    
    scenarios = [
        TestScenarios.lion_scenario(),
        TestScenarios.bus_scenario(),
        TestScenarios.eye_contact_scenario()
    ]
    
    results = []
    
    for i, scenario in enumerate(scenarios, 1):
        print(f"\n{'=' * 70}")
        print(f"Test {i}/{len(scenarios)}: {scenario['name']}")
        print(f"{'=' * 70}")
        print(f"Context: {scenario['context']}")
        print(f"\nTranscript:\n{scenario['transcript']}")
        
        # Run inference
        raw_output = agent.run_inference(
            transcript_input=scenario['transcript'],
            context=scenario['context']
        )
        
        # Validate output
        success, data, message = process_and_validate(raw_output)
        
        print(f"\n📊 Validation: {message}")
        
        if success:
            print("\n✨ Structured Output:")
            print(json.dumps(data, indent=2, ensure_ascii=False))
            
            # Check for expected keywords
            output_text = json.dumps(data, ensure_ascii=False)
            keywords_found = [kw for kw in scenario['expected_keywords'] if kw in output_text]
            
            print(f"\n🔍 Keyword Check: {len(keywords_found)}/{len(scenario['expected_keywords'])} found")
            print(f"   Found: {', '.join(keywords_found)}")
            
            results.append({
                "scenario": scenario['name'],
                "success": True,
                "keywords_found": len(keywords_found),
                "keywords_total": len(scenario['expected_keywords'])
            })
        else:
            print(f"\n❌ Test failed: {message}")
            results.append({
                "scenario": scenario['name'],
                "success": False
            })
    
    # Summary
    print(f"\n{'=' * 70}")
    print("📈 Test Suite Summary")
    print(f"{'=' * 70}")
    
    passed = sum(1 for r in results if r['success'])
    total = len(results)
    
    print(f"\nTests Passed: {passed}/{total}")
    
    for result in results:
        status = "✅" if result['success'] else "❌"
        print(f"{status} {result['scenario']}")
        if result['success'] and 'keywords_found' in result:
            print(f"   Keywords: {result['keywords_found']}/{result['keywords_total']}")
    
    print(f"\n{'=' * 70}")
    if passed == total:
        print("🎉 All tests passed!")
    else:
        print(f"⚠️  {total - passed} test(s) failed")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    run_test_suite()
