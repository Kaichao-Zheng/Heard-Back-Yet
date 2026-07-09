# View Definition

v_application_overview
回答：我投了哪些岗位，现在各自是什么状态？作为业务查询主入口，它是快照而不是历史

v_application_timeline
回答：某家公司是怎么一步步推进的？以归一化 company 为粒度，仅保留 `applied`、`assessment`、`interview`、`offer`、`rejection` 状态事件。

v_application_evidence
回答：为什么系统认为这个 application 是这个状态 / 这个公司 / 这个岗位？作为explainability layer

v_inconsistent_status_snapshot
回答：哪些 application 的 status snapshot 指针和被指向的 email fact 不一致，需要人工 review

v_unlinked_status_email
回答：哪些 status-driving 邮件还没成功挂到 application 上，需要人工 review


# Sample Questions

- What are the N latest `status` updates?

  最新的N条申请进度更新是什么？

  Key fields:

  `company_name`, `position_name`, `latest_status`, `latest_status_received_at`

- How many `applications` were submitted in the last N days?

  这N天投了几家`company`？

  Key fields:

  `application_id`, `company_name`, `position_name`, `email_type`, `received_at`

- How many `companies` were submitted to in month X?

  X月投了几家公司？

  Key fields:

  `company_name`, `email_type`, `received_at`

- What's the `status` with `company`?

  `company`那边的进展如何？

  Key fields:

  `company_name`, `position_name`, `latest_status`, `latest_status_received_at`

- How did things progress with `company`?

  `company` 那边是怎么推进的？

  Key fields:

  `company_name`, `position_name`, `email_type`, `received_at`

- What did `company` say in their reply?

  `company` 的回信里怎么说？

  Key fields:

  `application_id`, `company_name`, `position_name`, `latest_status`, `latest_status_received_at`, `subject`

- What are the requirements for `company`?

  `company`的工作有什么要求？

  Key fields:

  `company_name`, `position_name`, `captured_at`, `responsibilities`, `qualifications`, `source_url`
