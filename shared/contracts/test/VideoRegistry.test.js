const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("VideoRegistry", function () {
  let videoRegistry;
  let owner, node1, node2, unauthorized;

  const sampleHash = ethers.id("sample_video_content_bytes");
  const sampleHash2 = ethers.id("another_video_content_bytes");
  const perceptualHash =
    "FA3B7D2E-D2C1E4F3-E1F2A3B4-A4B5C6D7-B1C2D3E4";
  const ipHash = ethers.id("192.168.1.100");

  beforeEach(async function () {
    [owner, node1, node2, unauthorized] = await ethers.getSigners();

    const VideoRegistry = await ethers.getContractFactory("VideoRegistry");
    videoRegistry = await VideoRegistry.deploy();
    await videoRegistry.waitForDeployment();

    // Authorize node1
    await videoRegistry.authorizeNode(node1.address, "Pi-Node-001", "pi");
  });

  describe("Video Registration", function () {
    it("should register a new video", async function () {
      await videoRegistry
        .connect(node1)
        .registerVideo(
          sampleHash,
          perceptualHash,
          true,
          8500,
          2341,
          7650,
          ipHash,
          "United States",
          "New York",
          40774900,
          -73968500,
          '{"model":"CNN"}'
        );

      const video = await videoRegistry.getVideo(sampleHash);
      expect(video.isDeepfake).to.equal(true);
      expect(video.confidence).to.equal(8500);
      expect(video.detectionCount).to.equal(1);
      expect(video.country).to.equal("United States");
      expect(video.city).to.equal("New York");
    });

    it("should emit VideoRegistered event", async function () {
      await expect(
        videoRegistry
          .connect(node1)
          .registerVideo(
            sampleHash, perceptualHash, true, 8500, 2341, 7650,
            ipHash, "US", "NY", 0, 0, "{}"
          )
      )
        .to.emit(videoRegistry, "VideoRegistered")
        .withArgs(sampleHash, true, 8500, node1.address, await getBlockTimestamp());
    });

    it("should emit DeepfakeDetected event for deepfakes", async function () {
      await expect(
        videoRegistry
          .connect(node1)
          .registerVideo(
            sampleHash, perceptualHash, true, 9000, 0, 0,
            ipHash, "India", "Delhi", 0, 0, "{}"
          )
      ).to.emit(videoRegistry, "DeepfakeDetected");
    });

    it("should emit AuthenticVideoConfirmed for non-deepfakes", async function () {
      await expect(
        videoRegistry
          .connect(node1)
          .registerVideo(
            sampleHash, perceptualHash, false, 9000, 8000, 9500,
            ipHash, "UK", "London", 0, 0, "{}"
          )
      ).to.emit(videoRegistry, "AuthenticVideoConfirmed");
    });

    it("should increment detection count on re-detection", async function () {
      // First detection
      await videoRegistry
        .connect(node1)
        .registerVideo(
          sampleHash, perceptualHash, true, 8500, 2341, 7650,
          ipHash, "US", "NY", 0, 0, "{}"
        );

      // Second detection
      const ipHash2 = ethers.id("10.0.0.1");
      await videoRegistry
        .connect(node1)
        .registerVideo(
          sampleHash, perceptualHash, true, 8500, 2341, 7650,
          ipHash2, "UK", "London", 0, 0, "{}"
        );

      const video = await videoRegistry.getVideo(sampleHash);
      expect(video.detectionCount).to.equal(2);
    });

    it("should emit VideoRedetected on re-detection", async function () {
      await videoRegistry
        .connect(node1)
        .registerVideo(
          sampleHash, perceptualHash, true, 8500, 0, 0,
          ipHash, "US", "NY", 0, 0, "{}"
        );

      const ipHash2 = ethers.id("10.0.0.1");
      await expect(
        videoRegistry
          .connect(node1)
          .registerVideo(
            sampleHash, perceptualHash, true, 8500, 0, 0,
            ipHash2, "UK", "London", 0, 0, "{}"
          )
      )
        .to.emit(videoRegistry, "VideoRedetected")
        .withArgs(sampleHash, 2, ipHash2, await getBlockTimestamp());
    });

    it("should reject invalid content hash", async function () {
      await expect(
        videoRegistry
          .connect(node1)
          .registerVideo(
            ethers.ZeroHash, perceptualHash, true, 8500, 0, 0,
            ipHash, "US", "NY", 0, 0, "{}"
          )
      ).to.be.revertedWith("VideoRegistry: invalid content hash");
    });

    it("should reject confidence > 10000", async function () {
      await expect(
        videoRegistry
          .connect(node1)
          .registerVideo(
            sampleHash, perceptualHash, true, 10001, 0, 0,
            ipHash, "US", "NY", 0, 0, "{}"
          )
      ).to.be.revertedWith("VideoRegistry: confidence exceeds 10000");
    });

    it("should reject unauthorized nodes", async function () {
      await expect(
        videoRegistry
          .connect(unauthorized)
          .registerVideo(
            sampleHash, perceptualHash, true, 8500, 0, 0,
            ipHash, "US", "NY", 0, 0, "{}"
          )
      ).to.be.revertedWith("AccessControl: caller is not authorized");
    });
  });

  describe("Similarity Search", function () {
    it("should find similar videos by perceptual hash", async function () {
      await videoRegistry
        .connect(node1)
        .registerVideo(
          sampleHash, perceptualHash, true, 8500, 0, 0,
          ipHash, "US", "NY", 0, 0, "{}"
        );

      const similar = await videoRegistry.findSimilarVideos(perceptualHash);
      expect(similar.length).to.equal(1);
      expect(similar[0]).to.equal(sampleHash);
    });

    it("should group videos with same perceptual hash", async function () {
      await videoRegistry
        .connect(node1)
        .registerVideo(
          sampleHash, perceptualHash, true, 8500, 0, 0,
          ipHash, "US", "NY", 0, 0, "{}"
        );

      await videoRegistry
        .connect(node1)
        .registerVideo(
          sampleHash2, perceptualHash, true, 7500, 0, 0,
          ipHash, "UK", "London", 0, 0, "{}"
        );

      const similar = await videoRegistry.findSimilarVideos(perceptualHash);
      expect(similar.length).to.equal(2);
    });
  });

  describe("Statistics", function () {
    it("should track total videos", async function () {
      await videoRegistry
        .connect(node1)
        .registerVideo(
          sampleHash, perceptualHash, true, 8500, 0, 0,
          ipHash, "US", "NY", 0, 0, "{}"
        );

      expect(await videoRegistry.getTotalVideos()).to.equal(1);
    });

    it("should track deepfake vs authentic counts", async function () {
      await videoRegistry
        .connect(node1)
        .registerVideo(
          sampleHash, perceptualHash, true, 8500, 0, 0,
          ipHash, "US", "NY", 0, 0, "{}"
        );

      await videoRegistry
        .connect(node1)
        .registerVideo(
          sampleHash2, perceptualHash, false, 9000, 0, 0,
          ipHash, "US", "NY", 0, 0, "{}"
        );

      const [total, deepfakes, authentic] = await videoRegistry.getStats();
      expect(total).to.equal(2);
      expect(deepfakes).to.equal(1);
      expect(authentic).to.equal(1);
    });
  });

  describe("Batch Registration", function () {
    it("should batch register multiple videos", async function () {
      const hashes = [sampleHash, sampleHash2];
      const pHashes = [perceptualHash, "AAAA-BBBB-CCCC-DDDD-EEEE"];
      const isDeepfakes = [true, false];
      const confidences = [8500, 9200];
      const ipHashes = [ipHash, ipHash];
      const countries = ["US", "UK"];
      const cities = ["NY", "London"];

      await videoRegistry
        .connect(node1)
        .batchRegisterVideos(
          hashes, pHashes, isDeepfakes, confidences, ipHashes, countries, cities
        );

      expect(await videoRegistry.getTotalVideos()).to.equal(2);
      
      const video1 = await videoRegistry.getVideo(sampleHash);
      expect(video1.isDeepfake).to.equal(true);
      
      const video2 = await videoRegistry.getVideo(sampleHash2);
      expect(video2.isDeepfake).to.equal(false);
    });
  });

  // Helper to get approximate current block timestamp
  async function getBlockTimestamp() {
    const block = await ethers.provider.getBlock("latest");
    return block.timestamp + 1; // Approximate next block timestamp
  }
});
