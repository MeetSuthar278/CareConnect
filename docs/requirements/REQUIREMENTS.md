# CareConnect – System Requirements

**Group 4 | ENSF 607 | University of Calgary**

## 1. Purpose

CareConnect connects community members with approved organizations that provide non-medical support. It supports SDG 17 by improving cooperation between organizations and SDG 3 by improving access to community wellness services.

## 2. Functional Requirements

| ID | Requirement |
|---|---|
| FR-01 | Members and organization representatives can register and verify their email. |
| FR-02 | Users can log in and reset their password. |
| FR-03 | Members can manage their personal profile. |
| FR-04 | Members can search available services. |
| FR-05 | Members can submit requests with a location and time frame. |
| FR-06 | Members can track their request progress. |
| FR-07 | Members can provide feedback after service completion. |
| FR-08 | Organizations can apply for approval. |
| FR-09 | Representatives can manage their organization profile. |
| FR-10 | Representatives can manage services, capacity and availability. |
| FR-11 | Representatives can accept or reject referrals. |
| FR-12 | Representatives can record attendance and service completion. |
| FR-13 | Coordinators can review organization applications. |
| FR-14 | Coordinators can manage approved organizations. |
| FR-15 | Coordinators can view, filter and monitor requests. |
| FR-16 | Coordinators can review request and referral history. |
| FR-17 | Coordinators can manually assign eligible organizations. |
| FR-18 | Coordinators can view reports. |
| FR-19 | The system automatically matches eligible organizations. |
| FR-20 | The system creates referrals and reserves capacity. |
| FR-21 | The system tries backup organizations after rejection or timeout. |
| FR-22 | The system monitors response and attendance deadlines. |
| FR-23 | The system alerts coordinators when assistance is delayed or unavailable. |
| FR-24 | The system sends in-app notifications. |

## 3. Non-Functional Requirements

| ID | Area | Requirement |
|---|---|---|
| NFR-01 | Security | Use Firebase authentication and role-based access. |
| NFR-02 | Privacy | Restrict access to private user information. |
| NFR-03 | Reliability | Prevent duplicate active referrals when events are repeated. |
| NFR-04 | Usability | Provide clear wording, simple forms and responsive pages. |
| NFR-05 | Performance | Filter and sort database records before pagination. |
| NFR-06 | Maintainability | Use separate modules with clear responsibilities. |
| NFR-07 | Data integrity | Use database constraints to maintain consistent records. |
| NFR-08 | Recoverability | Store events and deadlines to support recovery after interruptions. |

## 4. Business Rules

| ID | Rule |
|---|---|
| BR-01 | Time frames are 6, 12 and 24 hours to start assistance, not to complete it. |
| BR-02 | Matching considers organization approval, active services, location, supported time frame and capacity. Eligible organizations are ranked by active referrals, acceptance rate and on-time attendance. |
| BR-03 | Only one referral can be active at a time. A maximum of three attempts is allowed without resetting the original deadline. Expired referrals cannot be accepted. |
| BR-04 | Acceptance, attendance and completion are separate stages. Missing the attendance deadline alerts the coordinator. |
| BR-05 | When no eligible organization is available, the member is informed and the coordinator is alerted. The original time frame is not lowered. |
| BR-06 | Member contact details are shared with the assigned organization after acceptance. Feedback uses Yes/No answers with an optional comment. Negative feedback alerts the coordinator. |

## 5. System Scope

CareConnect provides community support referrals. It does not provide medical treatment or emergency assistance.

Service notifications are provided within the application. Firebase handles account verification and password reset emails.

These requirements describe the intended system behaviour and do not guarantee production-level availability or security.
