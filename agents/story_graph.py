"""
Story Graph Utilities
~~~~~~~~~~~~~~~~~~~~~
支持从树状结构迁移到 DAG 的工具函数
"""

from typing import Dict, List, Set, Tuple, Any
import logging

logger = logging.getLogger(__name__)


class StoryGraph:
    """故事图结构（支持树和DAG）"""
    
    def __init__(self, data: Dict[str, Any]):
        """
        初始化故事图
        
        Args:
            data: 游戏设计数据，必须包含 story_graph
        """
        self.nodes = {}
        self.edges = []
        self.adjacency = {}  # {node_id: [(target_id, choice_text), ...]}
        self.reverse_adjacency = {}  # {node_id: [parent_id, ...]}
        
        if 'story_graph' not in data:
            raise ValueError("游戏设计数据中缺少 story_graph 字段")
        
        self._load_dag_format(data['story_graph'])
    
    def _load_dag_format(self, story_graph: Dict[str, Any]):
        """加载 DAG 格式的数据"""
        self.nodes = story_graph.get('nodes', {})
        self.edges = story_graph.get('edges', [])
        
        # 构建邻接表
        self.adjacency = {node_id: [] for node_id in self.nodes}
        self.reverse_adjacency = {node_id: [] for node_id in self.nodes}
        
        for edge in self.edges:
            from_node = edge['from']
            to_node = edge['to']
            choice_text = edge.get('choice_text')
            
            self.adjacency[from_node].append((to_node, choice_text))
            self.reverse_adjacency[to_node].append(from_node)
        
        logger.info(f"✅ 加载故事图：{len(self.nodes)} 个节点，{len(self.edges)} 条边")
    
    def get_children(self, node_id: str) -> List[Tuple[str, str]]:
        """
        获取节点的子节点
        
        Returns:
            [(child_id, choice_text), ...]
        """
        return self.adjacency.get(node_id, [])
    
    def get_parents(self, node_id: str) -> List[str]:
        """获取节点的父节点（DAG 中可能有多个）"""
        return self.reverse_adjacency.get(node_id, [])
    
    def get_node(self, node_id: str) -> Dict[str, Any]:
        """获取节点数据"""
        return self.nodes.get(node_id, {})
    
    def is_merge_point(self, node_id: str) -> bool:
        """判断是否为汇合点（有多个父节点）"""
        return len(self.get_parents(node_id)) > 1
    
    def topological_sort(self) -> List[str]:
        """
        拓扑排序（用于生成剧情时的遍历顺序）
        
        Returns:
            节点ID列表，按依赖顺序排列
        """
        in_degree = {node_id: len(self.get_parents(node_id)) for node_id in self.nodes}
        queue = [node_id for node_id, degree in in_degree.items() if degree == 0]
        result = []
        
        while queue:
            node_id = queue.pop(0)
            result.append(node_id)
            
            for child_id, _ in self.get_children(node_id):
                in_degree[child_id] -= 1
                if in_degree[child_id] == 0:
                    queue.append(child_id)
        
        if len(result) != len(self.nodes):
            logger.error("❌ 图中存在环路！拓扑排序失败")
            return []
        
        return result
    
    def validate(self) -> Tuple[bool, str]:
        """
        验证图的有效性
        
        Returns:
            (is_valid, error_message)
        """
        # 检查所有边引用的节点是否存在
        for edge in self.edges:
            if edge['from'] not in self.nodes:
                return False, f"边引用了不存在的源节点: {edge['from']}"
            if edge['to'] not in self.nodes:
                return False, f"边引用了不存在的目标节点: {edge['to']}"
        
        # 检查是否有环路
        sorted_nodes = self.topological_sort()
        if not sorted_nodes:
            return False, "图中存在环路"
        
        # 检查是否有起始节点
        if 'root' not in self.nodes:
            return False, "缺少 root 起始节点"
        
        return True, "验证通过"
    
    def to_dict(self) -> Dict[str, Any]:
        """转换回字典格式"""
        return {
            'nodes': self.nodes,
            'edges': self.edges
        }
    
    def get_reachable_endings(self, from_node: str) -> List[str]:
        """
        获取从指定节点可达的所有结局
        
        Args:
            from_node: 起始节点ID
            
        Returns:
            结局节点ID列表
        """
        visited = set()
        endings = []
        
        def dfs(node_id: str):
            if node_id in visited:
                return
            visited.add(node_id)
            
            children = self.get_children(node_id)
            if not children:
                # 叶子节点即结局
                endings.append(node_id)
            else:
                for child_id, _ in children:
                    dfs(child_id)
        
        dfs(from_node)
        return endings
