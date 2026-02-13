const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("TrackingLedger", function () {
  let trackingLedger;
  let owner, node1, node2;

  const videoHash = ethers.id("test_video_bytes");
  const videoHash2 = ethers.id("test_video_2_bytes");
  const ipHash1 = ethers.id("192.168.1.100");
  const ipHash2 = ethers.id("10.0.0.50");
  const ipHash3 = ethers.id("172.16.0.1");

  beforeEach(async function () {
    [owner, node1, node2] = await ethers.getSigners();

    const TrackingLedger = await ethers.getContractFactory("TrackingLedger");
    trackingLedger = await TrackingLedger.deploy();
    await trackingLedger.waitForDeployment();

    await trackingLedger.authorizeNode(node1.address, "Pi-Node-001", "pi");
    await trackingLedger.authorizeNode(node2.address, "Laptop-Host", "laptop");
  });

  describe("Spread Events", function () {
    it("should record a spread event", async function () {
      await trackingLedger
        .connect(node1)
        .recordSpreadEvent(
          videoHash,
          ipHash1,
          "United States",
          "New York",
          40774900,
          -73968500,
          "youtube",
          '{"url":"https://youtube.com/..."}'
        );

      const count = await trackingLedger.getSpreadCount(videoHash);
      expect(count).to.equal(1);
    });

    it("should emit SpreadRecorded event", async function () {
      await expect(
        trackingLedger
          .connect(node1)
          .recordSpreadEvent(
            videoHash, ipHash1, "US", "NY", 0, 0, "twitter", "{}"
          )
      ).to.emit(trackingLedger, "SpreadRecorded");
    });

    it("should detect same-IP re-upload", async function () {
      // First upload from IP
      await trackingLedger
        .connect(node1)
        .recordSpreadEvent(
          videoHash, ipHash1, "US", "NY", 0, 0, "youtube", "{}"
        );

      // Second upload from same IP
      await expect(
        trackingLedger
          .connect(node1)
          .recordSpreadEvent(
            videoHash, ipHash1, "US", "NY", 0, 0, "twitter", "{}"
          )
      ).to.emit(trackingLedger, "SameIPReupload");
    });

    it("should detect new location spread", async function () {
      // Upload from US
      await trackingLedger
        .connect(node1)
        .recordSpreadEvent(
          videoHash, ipHash1, "United States", "NY", 0, 0, "youtube", "{}"
        );

      // Upload from UK (new country)
      await expect(
        trackingLedger
          .connect(node1)
          .recordSpreadEvent(
            videoHash, ipHash2, "United Kingdom", "London", 0, 0, "twitter", "{}"
          )
      ).to.emit(trackingLedger, "NewLocationSpread");
    });

    it("should NOT emit NewLocationSpread for same country", async function () {
      await trackingLedger
        .connect(node1)
        .recordSpreadEvent(
          videoHash, ipHash1, "US", "NY", 0, 0, "youtube", "{}"
        );

      // Same country different city
      await expect(
        trackingLedger
          .connect(node1)
          .recordSpreadEvent(
            videoHash, ipHash2, "US", "LA", 0, 0, "twitter", "{}"
          )
      ).to.not.emit(trackingLedger, "NewLocationSpread");
    });

    it("should track unique country count", async function () {
      await trackingLedger
        .connect(node1)
        .recordSpreadEvent(
          videoHash, ipHash1, "US", "NY", 0, 0, "youtube", "{}"
        );

      await trackingLedger
        .connect(node1)
        .recordSpreadEvent(
          videoHash, ipHash2, "UK", "London", 0, 0, "twitter", "{}"
        );

      await trackingLedger
        .connect(node1)
        .recordSpreadEvent(
          videoHash, ipHash3, "Germany", "Berlin", 0, 0, "facebook", "{}"
        );

      const uniqueCountries = await trackingLedger.getUniqueCountryCount(videoHash);
      expect(uniqueCountries).to.equal(3);
    });

    it("should emit ViralSpreadWarning at thresholds", async function () {
      // Record 9 events first
      for (let i = 0; i < 9; i++) {
        const ip = ethers.id(`ip_${i}`);
        await trackingLedger
          .connect(node1)
          .recordSpreadEvent(
            videoHash, ip, `Country_${i}`, `City_${i}`, 0, 0, "platform", "{}"
          );
      }

      // 10th event should trigger ViralSpreadWarning
      const ip10 = ethers.id("ip_10");
      await expect(
        trackingLedger
          .connect(node1)
          .recordSpreadEvent(
            videoHash, ip10, "Country_10", "City_10", 0, 0, "platform", "{}"
          )
      ).to.emit(trackingLedger, "ViralSpreadWarning");
    });

    it("should reject unauthorized nodes", async function () {
      const [, , , unauth] = await ethers.getSigners();
      await expect(
        trackingLedger
          .connect(unauth)
          .recordSpreadEvent(
            videoHash, ipHash1, "US", "NY", 0, 0, "youtube", "{}"
          )
      ).to.be.revertedWith("AccessControl: caller is not authorized");
    });
  });

  describe("Lineage Tracking", function () {
    it("should register lineage relationship", async function () {
      await trackingLedger
        .connect(node1)
        .registerLineage(
          videoHash,
          videoHash2,
          8500,
          "frame-splice",
          '{"frames":"10-50"}'
        );

      const lineages = await trackingLedger.getLineage(videoHash);
      expect(lineages.length).to.equal(1);
      expect(lineages[0].childHash).to.equal(videoHash2);
      expect(lineages[0].similarityScore).to.equal(8500);
    });

    it("should emit LineageRegistered event", async function () {
      await expect(
        trackingLedger
          .connect(node1)
          .registerLineage(videoHash, videoHash2, 9000, "reencode", "{}")
      ).to.emit(trackingLedger, "LineageRegistered");
    });

    it("should reject self-referencing lineage", async function () {
      await expect(
        trackingLedger
          .connect(node1)
          .registerLineage(videoHash, videoHash, 10000, "self", "{}")
      ).to.be.revertedWith("TrackingLedger: self-reference");
    });

    it("should reject invalid similarity score", async function () {
      await expect(
        trackingLedger
          .connect(node1)
          .registerLineage(videoHash, videoHash2, 10001, "invalid", "{}")
      ).to.be.revertedWith("TrackingLedger: invalid score");
    });
  });

  describe("IP Upload Tracking", function () {
    it("should track IP upload count per video", async function () {
      await trackingLedger
        .connect(node1)
        .recordSpreadEvent(
          videoHash, ipHash1, "US", "NY", 0, 0, "youtube", "{}"
        );

      await trackingLedger
        .connect(node1)
        .recordSpreadEvent(
          videoHash, ipHash1, "US", "NY", 0, 0, "twitter", "{}"
        );

      const count = await trackingLedger.getIPUploadCount(videoHash, ipHash1);
      expect(count).to.equal(2);
    });

    it("should track different IPs separately", async function () {
      await trackingLedger
        .connect(node1)
        .recordSpreadEvent(videoHash, ipHash1, "US", "NY", 0, 0, "yt", "{}");

      await trackingLedger
        .connect(node1)
        .recordSpreadEvent(videoHash, ipHash2, "UK", "London", 0, 0, "yt", "{}");

      const count1 = await trackingLedger.getIPUploadCount(videoHash, ipHash1);
      const count2 = await trackingLedger.getIPUploadCount(videoHash, ipHash2);
      expect(count1).to.equal(1);
      expect(count2).to.equal(1);
    });
  });

  describe("Spread History", function () {
    it("should return spread events for a video", async function () {
      await trackingLedger
        .connect(node1)
        .recordSpreadEvent(videoHash, ipHash1, "US", "NY", 0, 0, "yt", "{}");

      await trackingLedger
        .connect(node1)
        .recordSpreadEvent(videoHash, ipHash2, "UK", "London", 0, 0, "tw", "{}");

      const events = await trackingLedger.getSpreadHistory(videoHash);
      expect(events.length).to.equal(2);
      expect(events[0].platform).to.equal("yt");
      expect(events[1].platform).to.equal("tw");
    });
  });
});
