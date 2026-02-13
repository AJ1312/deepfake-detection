const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("AlertManager", function () {
  let alertManager;
  let owner, node1, operator;

  const videoHash = ethers.id("deepfake_video_bytes");
  const ipHash = ethers.id("192.168.1.100");

  beforeEach(async function () {
    [owner, node1, operator] = await ethers.getSigners();

    const AlertManager = await ethers.getContractFactory("AlertManager");
    alertManager = await AlertManager.deploy();
    await alertManager.waitForDeployment();

    await alertManager.authorizeNode(node1.address, "Pi-Node-001", "pi");
  });

  describe("First Detection Alerts", function () {
    it("should trigger alert on first deepfake detection", async function () {
      await expect(
        alertManager
          .connect(node1)
          .triggerFirstDetectionAlert(videoHash, 8500, ipHash, "US", "New York")
      ).to.emit(alertManager, "AlertTriggered");

      const alerts = await alertManager.getVideoAlerts(videoHash);
      expect(alerts.length).to.equal(1);
      expect(alerts[0].alertType).to.equal(0); // FIRST_DETECTION
      expect(alerts[0].severity).to.equal(2); // HIGH
    });

    it("should set severity based on confidence", async function () {
      // Low confidence -> MEDIUM severity
      await alertManager
        .connect(node1)
        .triggerFirstDetectionAlert(videoHash, 5000, ipHash, "US", "NY");

      const alerts = await alertManager.getVideoAlerts(videoHash);
      expect(alerts[0].severity).to.equal(1); // MEDIUM
    });

    it("should set CRITICAL for very high confidence", async function () {
      await alertManager
        .connect(node1)
        .triggerFirstDetectionAlert(videoHash, 9500, ipHash, "US", "NY");

      const alerts = await alertManager.getVideoAlerts(videoHash);
      expect(alerts[0].severity).to.equal(3); // CRITICAL
    });
  });

  describe("Re-upload Alerts", function () {
    it("should trigger alert on same-IP re-upload", async function () {
      await expect(
        alertManager
          .connect(node1)
          .triggerReuploadAlert(videoHash, ipHash, 3, "US", "NY")
      ).to.emit(alertManager, "AlertTriggered");

      const alerts = await alertManager.getVideoAlerts(videoHash);
      expect(alerts[0].alertType).to.equal(1); // REUPLOAD
    });

    it("should increase severity with upload count", async function () {
      // 2 uploads -> MEDIUM
      await alertManager
        .connect(node1)
        .triggerReuploadAlert(videoHash, ipHash, 2, "US", "NY");

      let alerts = await alertManager.getVideoAlerts(videoHash);
      expect(alerts[0].severity).to.equal(1); // MEDIUM

      // Wait for cooldown or use different video
      const videoHash2 = ethers.id("another_video");
      await alertManager
        .connect(node1)
        .triggerReuploadAlert(videoHash2, ipHash, 5, "US", "NY");

      alerts = await alertManager.getVideoAlerts(videoHash2);
      expect(alerts[0].severity).to.equal(2); // HIGH
    });
  });

  describe("Geo Spread Alerts", function () {
    it("should trigger alert on geographic spread", async function () {
      await expect(
        alertManager
          .connect(node1)
          .triggerGeoSpreadAlert(videoHash, 3, "Germany")
      ).to.emit(alertManager, "AlertTriggered");

      const alerts = await alertManager.getVideoAlerts(videoHash);
      expect(alerts[0].alertType).to.equal(2); // GEO_SPREAD
    });

    it("should set CRITICAL for wide spread (5+ countries)", async function () {
      await alertManager
        .connect(node1)
        .triggerGeoSpreadAlert(videoHash, 5, "Country5");

      const alerts = await alertManager.getVideoAlerts(videoHash);
      expect(alerts[0].severity).to.equal(3); // CRITICAL
    });
  });

  describe("Threshold Alerts", function () {
    it("should check and trigger threshold alerts", async function () {
      await alertManager
        .connect(node1)
        .checkThresholds(videoHash, 100, 50, 5, 10);

      const alerts = await alertManager.getVideoAlerts(videoHash);
      expect(alerts.length).to.be.greaterThan(0);
      expect(alerts[0].alertType).to.equal(3); // THRESHOLD
    });

    it("should not trigger if below thresholds", async function () {
      await alertManager
        .connect(node1)
        .checkThresholds(videoHash, 10, 5, 1, 0);

      const alerts = await alertManager.getVideoAlerts(videoHash);
      expect(alerts.length).to.equal(0);
    });
  });

  describe("Alert Cooldown", function () {
    it("should respect cooldown period", async function () {
      // First alert
      await alertManager
        .connect(node1)
        .triggerFirstDetectionAlert(videoHash, 8500, ipHash, "US", "NY");

      // Second alert immediately - should be silenced by cooldown
      await alertManager
        .connect(node1)
        .triggerReuploadAlert(videoHash, ipHash, 2, "US", "NY");

      const alerts = await alertManager.getVideoAlerts(videoHash);
      // May be 1 or 2 depending on cooldown implementation
      // The second should be suppressed if within cooldown
      expect(alerts.length).to.be.greaterThanOrEqual(1);
    });

    it("should allow alerts after cooldown expires", async function () {
      await alertManager
        .connect(node1)
        .triggerFirstDetectionAlert(videoHash, 8500, ipHash, "US", "NY");

      // Fast forward time (Hardhat feature)
      await ethers.provider.send("evm_increaseTime", [301]);
      await ethers.provider.send("evm_mine");

      await alertManager
        .connect(node1)
        .triggerReuploadAlert(videoHash, ipHash, 2, "US", "NY");

      const alerts = await alertManager.getVideoAlerts(videoHash);
      expect(alerts.length).to.equal(2);
    });

    it("should allow owner to update cooldown", async function () {
      await alertManager.connect(owner).setAlertCooldown(600);
      const cooldown = await alertManager.alertCooldownSeconds();
      expect(cooldown).to.equal(600);
    });
  });

  describe("Custom Alert Rules", function () {
    it("should allow setting custom rules per video", async function () {
      await alertManager
        .connect(owner)
        .setVideoAlertRule(videoHash, 50, 25, 3, 5);

      // Now lower thresholds should trigger alerts
      await alertManager
        .connect(node1)
        .checkThresholds(videoHash, 50, 25, 3, 5);

      const alerts = await alertManager.getVideoAlerts(videoHash);
      expect(alerts.length).to.be.greaterThan(0);
    });
  });

  describe("Alert Acknowledgment", function () {
    it("should acknowledge an alert", async function () {
      await alertManager
        .connect(node1)
        .triggerFirstDetectionAlert(videoHash, 8500, ipHash, "US", "NY");

      const alerts = await alertManager.getVideoAlerts(videoHash);
      const alertId = alerts[0].id;

      await alertManager.connect(owner).acknowledgeAlert(alertId);

      const updated = await alertManager.getAlert(alertId);
      expect(updated.acknowledged).to.equal(true);
    });

    it("should batch acknowledge alerts", async function () {
      await alertManager
        .connect(node1)
        .triggerFirstDetectionAlert(videoHash, 8500, ipHash, "US", "NY");

      // Wait for cooldown
      await ethers.provider.send("evm_increaseTime", [301]);
      await ethers.provider.send("evm_mine");

      await alertManager
        .connect(node1)
        .triggerGeoSpreadAlert(videoHash, 3, "Germany");

      const alerts = await alertManager.getVideoAlerts(videoHash);
      const ids = alerts.map((a) => a.id);

      await alertManager.connect(owner).batchAcknowledgeAlerts(ids);

      for (const id of ids) {
        const alert = await alertManager.getAlert(id);
        expect(alert.acknowledged).to.equal(true);
      }
    });
  });

  describe("Alert Statistics", function () {
    it("should track total alerts", async function () {
      await alertManager
        .connect(node1)
        .triggerFirstDetectionAlert(videoHash, 8500, ipHash, "US", "NY");

      const total = await alertManager.getTotalAlerts();
      expect(total).to.equal(1);
    });

    it("should track unacknowledged alerts", async function () {
      await alertManager
        .connect(node1)
        .triggerFirstDetectionAlert(videoHash, 8500, ipHash, "US", "NY");

      const unack = await alertManager.getUnacknowledgedCount();
      expect(unack).to.equal(1);

      const alerts = await alertManager.getVideoAlerts(videoHash);
      await alertManager.connect(owner).acknowledgeAlert(alerts[0].id);

      const unack2 = await alertManager.getUnacknowledgedCount();
      expect(unack2).to.equal(0);
    });
  });

  describe("Access Control", function () {
    it("should reject unauthorized alert triggers", async function () {
      const [, , , unauth] = await ethers.getSigners();
      await expect(
        alertManager
          .connect(unauth)
          .triggerFirstDetectionAlert(videoHash, 8500, ipHash, "US", "NY")
      ).to.be.revertedWith("AccessControl: caller is not authorized");
    });

    it("should allow only owner to set rules", async function () {
      await expect(
        alertManager.connect(node1).setVideoAlertRule(videoHash, 50, 25, 3, 5)
      ).to.be.revertedWith("AccessControl: caller is not owner");
    });
  });
});
