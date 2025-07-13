# 💸 Veribroke – OpenCrafts Payment Gateway


`veribroke` is the official Java-based payment gateway for **OpenCrafts Interactive**, built with Spring Boot 3 and powered by the **Spring Modulith** architecture. It facilitates **in-app payments**, **external client integrations**, and supports **webhooks/callbacks** for real-time payment event notifications.

---

## 🚀 Features

- 🧩 **Modular design** using [Spring Modulith](https://docs.spring.io/spring-modulith/docs/current/reference/html/)
- 💸 Process internal app payments (subscriptions, top-ups, checkout flows)
- 📡 Expose webhook endpoints for external clients (mobile/web apps)
- 📈 Observability via Spring Actuator
- 📚 Auto-generated REST Docs with Spring REST Docs and AsciiDoctor
- ✅ Containerized testing support using **Testcontainers**
- 🔍 Production-ready from day one

---

## 🛠️ Tech Stack

| Tech             | Usage                          |
|------------------|-------------------------------|
| Java 21          | Primary language               |
| Spring Boot 3.5  | Core framework                 |
| Spring Modulith  | Modularity and lifecycle mgmt  |
| JPA              | ORM for DB integration         |
| Spring Actuator  | Metrics & health endpoints     |
| Spring REST Docs | Auto API documentation         |
| Testcontainers   | Integration tests              |
| GraalVM Native   | Optional native image builds   |

---

## 🧪 Running Locally

### Prerequisites

- Java 21
- Maven 3.8+
- PostgreSQL 

### 1. Clone the project

```bash
git clone https://github.com/opencrafts/veribroke.git
cd veribroke
```

### 2. Configure DB

Update `src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:postgresql://localhost:5432/veribroke
spring.datasource.username=youruser
spring.datasource.password=yourpass
spring.jpa.hibernate.ddl-auto=update
```

### 3. Run the app

```bash
./mvnw spring-boot:run
```

The app should be running at `http://localhost:8080`.

---

## 📡 API Usage

Once running, you'll have endpoints like:

- `POST /api/payments` – Initiate a payment
- `GET /api/payments/{id}` – Check payment status
- `POST /api/webhooks/payment-status` – Receive callbacks from external services

> ⚙️ API docs are auto-generated at build time under `target/generated-docs/`


## ✅ Testing

```bash
./mvnw test
```

Includes:

- ✅ Unit tests with JUnit 5
- 🔁 Integration tests with Testcontainers (PostgreSQL)
- 📄 REST Docs generation

---

## 📜 Building API Docs

```bash
./mvnw package
# See: target/generated-docs/index.html
```

---

## 🧊 Native Build (Optional)

If you're targeting a native runtime with GraalVM:

```bash
./mvnw -Pnative native:compile
```

---

## 🌍 Roadmap

- [ ] In-app payments
- [ ] External webhook support
- [ ] Admin dashboard for client management
- [ ] Integration with M-Pesa, Stripe, Flutterwave
- [ ] Retry/Dead-letter mechanism for webhook failures
- [ ] OAuth2 authentication for clients

---

## 💬 Contribution

Open to contributors! PRs and issues welcome.

1. Fork the repo
2. Create a feature branch
3. Push and open a PR

---

## 🛡 License

**Proprietary** – OpenCrafts internal use. External licensing upon request.

---

## 🧠 Maintainers

- Baraka Mnjala Mbugua  – [@eiidoubleyuwes](https://github.com/eiidoubleyuwes)
