"""Phase 3-B: 中央规则库和规则管理核心

提供系统规则、跨工作流关系、全局政策的存储、查询和版本控制机制。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Optional, Any

from . import db
from .models import (
    SystemRule, SystemRuleUpdate,
    WorkflowRelationship, WorkflowRelationshipUpdate,
    GlobalPolicy, GlobalPolicyUpdate,
    RuleValidationIssue, ImpactAnalysis,
    RuleStatus,
)

logger = logging.getLogger(__name__)


class RulesManager:
    """中央规则库管理器"""

    # 存储键前缀
    SYSTEM_RULES_KEY = "phase3b:system_rules"
    RELATIONSHIPS_KEY = "phase3b:relationships"
    POLICIES_KEY = "phase3b:policies"
    RULE_VERSIONS_KEY = "phase3b:rule_versions"

    @classmethod
    def create_system_rule(
        cls,
        rule_name: str,
        rule_type: str,
        description: str,
        content: dict,
        created_by: str,
        applicable_workflow_types: Optional[list[str]] = None,
        applicable_stages: Optional[list[str]] = None,
        requires_approval: bool = False,
        priority: str = "medium",
        tags: Optional[list[str]] = None,
    ) -> SystemRule:
        """创建系统规则"""
        from datetime import datetime
        from uuid import uuid4

        rule_id = f"rule_{uuid4().hex[:12]}"
        now = datetime.utcnow().isoformat() + "Z"

        rule = SystemRule(
            rule_id=rule_id,
            rule_name=rule_name,
            rule_type=rule_type,
            description=description,
            content=content,
            status="draft",
            applicable_workflow_types=applicable_workflow_types or [],
            applicable_stages=applicable_stages or [],
            version="1.0.0",
            effective_date=now,
            expiry_date=None,
            created_by=created_by,
            created_at=now,
            updated_by=created_by,
            updated_at=now,
            requires_approval=requires_approval,
            priority=priority,
            tags=tags or [],
        )

        # 存储规则
        rules = cls._load_system_rules()
        rules[rule_id] = rule.model_dump()
        cls._save_system_rules(rules)

        # 记录版本
        cls._record_version("system_rule", rule_id, "created", rule.model_dump(), created_by)

        logger.info(f"Created system rule: {rule_id} ({rule_name})")
        return rule

    @classmethod
    def get_system_rule(cls, rule_id: str) -> Optional[SystemRule]:
        """获取系统规则"""
        rules = cls._load_system_rules()
        if rule_id in rules:
            return SystemRule(**rules[rule_id])
        return None

    @classmethod
    def list_system_rules(
        cls,
        status: Optional[str] = None,
        rule_type: Optional[str] = None,
        workflow_type: Optional[str] = None,
    ) -> list[SystemRule]:
        """列表查询系统规则"""
        rules = cls._load_system_rules()

        result = []
        for rule_data in rules.values():
            rule = SystemRule(**rule_data)

            # 过滤条件
            if status and rule.status != status:
                continue
            if rule_type and rule.rule_type != rule_type:
                continue
            if workflow_type and workflow_type not in rule.applicable_workflow_types:
                if rule.applicable_workflow_types:  # 空列表表示全部
                    continue

            result.append(rule)

        return result

    @classmethod
    def update_system_rule(
        cls,
        rule_id: str,
        update_data: SystemRuleUpdate,
        updated_by: str,
    ) -> Optional[SystemRule]:
        """更新系统规则"""
        rule = cls.get_system_rule(rule_id)
        if not rule:
            return None

        # 只更新提供的字段
        update_dict = update_data.model_dump(exclude_unset=True)

        # 更新元数据
        now = datetime.utcnow().isoformat() + "Z"
        update_dict["updated_by"] = updated_by
        update_dict["updated_at"] = now

        # 版本升级（任何更新都应该促进版本升级）
        parts = rule.version.split(".")
        parts[-1] = str(int(parts[-1]) + 1)
        update_dict["version"] = ".".join(parts)

        # 应用更新
        for key, value in update_dict.items():
            if value is not None:
                setattr(rule, key, value)

        # 保存
        rules = cls._load_system_rules()
        rules[rule_id] = rule.model_dump()
        cls._save_system_rules(rules)

        # 记录版本
        cls._record_version("system_rule", rule_id, "updated", rule.model_dump(), updated_by)

        logger.info(f"Updated system rule: {rule_id}")
        return rule

    @classmethod
    def activate_system_rule(cls, rule_id: str, activated_by: str) -> Optional[SystemRule]:
        """激活系统规则（从draft到active）"""
        rule = cls.get_system_rule(rule_id)
        if not rule or rule.status != "draft":
            return None

        now = datetime.utcnow().isoformat() + "Z"
        update_data = SystemRuleUpdate(
            status="active",
        )

        updated_rule = cls.update_system_rule(rule_id, update_data, activated_by)
        if updated_rule:
            updated_rule.effective_date = now

        logger.info(f"Activated system rule: {rule_id}")
        return updated_rule

    # --- WorkflowRelationship 管理 ---

    @classmethod
    def create_workflow_relationship(
        cls,
        relationship_type: str,
        source_workflow_id: str,
        target_workflow_id: str,
        description: str,
        created_by: str,
        condition: Optional[str] = None,
        constraints: Optional[list] = None,
        tags: Optional[list[str]] = None,
    ) -> WorkflowRelationship:
        """创建工作流关系"""
        from uuid import uuid4

        rel_id = f"rel_{uuid4().hex[:12]}"
        now = datetime.utcnow().isoformat() + "Z"

        relationship = WorkflowRelationship(
            relationship_id=rel_id,
            relationship_type=relationship_type,
            source_workflow_id=source_workflow_id,
            target_workflow_id=target_workflow_id,
            description=description,
            condition=condition,
            constraints=constraints or [],
            version="1.0.0",
            status="active",
            created_by=created_by,
            created_at=now,
            updated_by=created_by,
            updated_at=now,
            tags=tags or [],
        )

        # 存储关系
        rels = cls._load_relationships()
        rels[rel_id] = relationship.model_dump()
        cls._save_relationships(rels)

        # 记录版本
        cls._record_version("relationship", rel_id, "created", relationship.model_dump(), created_by)

        logger.info(f"Created workflow relationship: {rel_id}")
        return relationship

    @classmethod
    def get_workflow_relationship(cls, rel_id: str) -> Optional[WorkflowRelationship]:
        """获取工作流关系"""
        rels = cls._load_relationships()
        if rel_id in rels:
            return WorkflowRelationship(**rels[rel_id])
        return None

    @classmethod
    def list_workflow_relationships(
        cls,
        source_workflow_id: Optional[str] = None,
        target_workflow_id: Optional[str] = None,
        relationship_type: Optional[str] = None,
    ) -> list[WorkflowRelationship]:
        """列表查询工作流关系"""
        rels = cls._load_relationships()

        result = []
        for rel_data in rels.values():
            rel = WorkflowRelationship(**rel_data)

            if source_workflow_id and rel.source_workflow_id != source_workflow_id:
                continue
            if target_workflow_id and rel.target_workflow_id != target_workflow_id:
                continue
            if relationship_type and rel.relationship_type != relationship_type:
                continue

            result.append(rel)

        return result

    @classmethod
    def update_workflow_relationship(
        cls,
        rel_id: str,
        update_data: WorkflowRelationshipUpdate,
        updated_by: str,
    ) -> Optional[WorkflowRelationship]:
        """更新工作流关系"""
        rel = cls.get_workflow_relationship(rel_id)
        if not rel:
            return None

        update_dict = update_data.model_dump(exclude_unset=True)

        now = datetime.utcnow().isoformat() + "Z"
        update_dict["updated_by"] = updated_by
        update_dict["updated_at"] = now

        # 版本升级
        if "constraints" in update_dict or "status" in update_dict:
            parts = rel.version.split(".")
            parts[-1] = str(int(parts[-1]) + 1)
            update_dict["version"] = ".".join(parts)

        for key, value in update_dict.items():
            if value is not None:
                setattr(rel, key, value)

        rels = cls._load_relationships()
        rels[rel_id] = rel.model_dump()
        cls._save_relationships(rels)

        cls._record_version("relationship", rel_id, "updated", rel.model_dump(), updated_by)

        logger.info(f"Updated workflow relationship: {rel_id}")
        return rel

    # --- GlobalPolicy 管理 ---

    @classmethod
    def create_global_policy(
        cls,
        policy_name: str,
        description: str,
        scope: str,
        created_by: str,
        scope_target: Optional[str] = None,
        decision_rules: Optional[list] = None,
        exception_handlers: Optional[list] = None,
        requires_approval: bool = False,
        priority: str = "medium",
        tags: Optional[list[str]] = None,
    ) -> GlobalPolicy:
        """创建全局政策"""
        from uuid import uuid4

        policy_id = f"policy_{uuid4().hex[:12]}"
        now = datetime.utcnow().isoformat() + "Z"

        policy = GlobalPolicy(
            policy_id=policy_id,
            policy_name=policy_name,
            description=description,
            scope=scope,
            scope_target=scope_target,
            decision_rules=decision_rules or [],
            exception_handlers=exception_handlers or [],
            version="1.0.0",
            status="draft",
            effective_date=now,
            expiry_date=None,
            created_by=created_by,
            created_at=now,
            updated_by=created_by,
            updated_at=now,
            requires_approval=requires_approval,
            priority=priority,
            tags=tags or [],
        )

        policies = cls._load_policies()
        policies[policy_id] = policy.model_dump()
        cls._save_policies(policies)

        cls._record_version("policy", policy_id, "created", policy.model_dump(), created_by)

        logger.info(f"Created global policy: {policy_id} ({policy_name})")
        return policy

    @classmethod
    def get_global_policy(cls, policy_id: str) -> Optional[GlobalPolicy]:
        """获取全局政策"""
        policies = cls._load_policies()
        if policy_id in policies:
            return GlobalPolicy(**policies[policy_id])
        return None

    @classmethod
    def list_global_policies(
        cls,
        scope: Optional[str] = None,
        status: Optional[str] = None,
    ) -> list[GlobalPolicy]:
        """列表查询全局政策"""
        policies = cls._load_policies()

        result = []
        for policy_data in policies.values():
            policy = GlobalPolicy(**policy_data)

            if scope and policy.scope != scope:
                continue
            if status and policy.status != status:
                continue

            result.append(policy)

        return result

    @classmethod
    def update_global_policy(
        cls,
        policy_id: str,
        update_data: GlobalPolicyUpdate,
        updated_by: str,
    ) -> Optional[GlobalPolicy]:
        """更新全局政策"""
        policy = cls.get_global_policy(policy_id)
        if not policy:
            return None

        update_dict = update_data.model_dump(exclude_unset=True)

        now = datetime.utcnow().isoformat() + "Z"
        update_dict["updated_by"] = updated_by
        update_dict["updated_at"] = now

        # 版本升级
        if any(k in update_dict for k in ["decision_rules", "exception_handlers", "status"]):
            parts = policy.version.split(".")
            parts[-1] = str(int(parts[-1]) + 1)
            update_dict["version"] = ".".join(parts)

        for key, value in update_dict.items():
            if value is not None:
                setattr(policy, key, value)

        policies = cls._load_policies()
        policies[policy_id] = policy.model_dump()
        cls._save_policies(policies)

        cls._record_version("policy", policy_id, "updated", policy.model_dump(), updated_by)

        logger.info(f"Updated global policy: {policy_id}")
        return policy

    # --- 内部存储方法 ---

    @classmethod
    def _load_system_rules(cls) -> dict:
        """从数据库加载系统规则"""
        try:
            rules_data = db.get_cache(cls.SYSTEM_RULES_KEY)
            if rules_data:
                return json.loads(rules_data) if isinstance(rules_data, str) else rules_data
        except Exception as e:
            logger.warning(f"Failed to load system rules: {e}")
        return {}

    @classmethod
    def _save_system_rules(cls, rules: dict) -> None:
        """保存系统规则到数据库"""
        try:
            db.set_cache(cls.SYSTEM_RULES_KEY, json.dumps(rules))
        except Exception as e:
            logger.error(f"Failed to save system rules: {e}")

    @classmethod
    def _load_relationships(cls) -> dict:
        """从数据库加载工作流关系"""
        try:
            rels_data = db.get_cache(cls.RELATIONSHIPS_KEY)
            if rels_data:
                return json.loads(rels_data) if isinstance(rels_data, str) else rels_data
        except Exception as e:
            logger.warning(f"Failed to load relationships: {e}")
        return {}

    @classmethod
    def _save_relationships(cls, relationships: dict) -> None:
        """保存工作流关系到数据库"""
        try:
            db.set_cache(cls.RELATIONSHIPS_KEY, json.dumps(relationships))
        except Exception as e:
            logger.error(f"Failed to save relationships: {e}")

    @classmethod
    def _load_policies(cls) -> dict:
        """从数据库加载全局政策"""
        try:
            policies_data = db.get_cache(cls.POLICIES_KEY)
            if policies_data:
                return json.loads(policies_data) if isinstance(policies_data, str) else policies_data
        except Exception as e:
            logger.warning(f"Failed to load policies: {e}")
        return {}

    @classmethod
    def _save_policies(cls, policies: dict) -> None:
        """保存全局政策到数据库"""
        try:
            db.set_cache(cls.POLICIES_KEY, json.dumps(policies))
        except Exception as e:
            logger.error(f"Failed to save policies: {e}")

    @classmethod
    def _record_version(
        cls,
        entity_type: str,
        entity_id: str,
        operation: str,
        entity_data: dict,
        user_id: str,
    ) -> None:
        """记录版本变更历史"""
        try:
            version_key = f"{cls.RULE_VERSIONS_KEY}:{entity_type}:{entity_id}"
            versions = db.get_cache(version_key)
            versions_list = json.loads(versions) if versions and isinstance(versions, str) else []

            now = datetime.utcnow().isoformat() + "Z"
            versions_list.append({
                "timestamp": now,
                "operation": operation,
                "user_id": user_id,
                "entity_data": entity_data,
            })

            # 只保留最近100条版本记录
            versions_list = versions_list[-100:]

            db.set_cache(version_key, json.dumps(versions_list))
        except Exception as e:
            logger.warning(f"Failed to record version: {e}")


# 导出主管理器
__all__ = ["RulesManager"]
