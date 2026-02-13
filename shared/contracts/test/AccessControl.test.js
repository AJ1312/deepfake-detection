const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("AccessControl", function () {
  let accessControl;
  let owner, node1, node2, unauthorized;

  beforeEach(async function () {
    [owner, node1, node2, unauthorized] = await ethers.getSigners();

    // Deploy VideoRegistry (which inherits AccessControl) for testing
    const VideoRegistry = await ethers.getContractFactory("VideoRegistry");
    accessControl = await VideoRegistry.deploy();
    await accessControl.waitForDeployment();
  });

  describe("Node Authorization", function () {
    it("should authorize a new node", async function () {
      await accessControl.authorizeNode(node1.address, "Pi-Node-001", "pi");

      const nodeInfo = await accessControl.getNodeInfo(node1.address);
      expect(nodeInfo.name).to.equal("Pi-Node-001");
      expect(nodeInfo.nodeType).to.equal("pi");
      expect(nodeInfo.active).to.equal(true);
    });

    it("should emit NodeAuthorized event", async function () {
      await expect(
        accessControl.authorizeNode(node1.address, "Pi-Node-001", "pi")
      )
        .to.emit(accessControl, "NodeAuthorized")
        .withArgs(node1.address, "Pi-Node-001", "pi");
    });

    it("should reject duplicate authorization", async function () {
      await accessControl.authorizeNode(node1.address, "Pi-Node-001", "pi");

      await expect(
        accessControl.authorizeNode(node1.address, "Pi-Node-002", "pi")
      ).to.be.revertedWith("AccessControl: already authorized");
    });

    it("should reject non-owner authorization", async function () {
      await expect(
        accessControl
          .connect(node1)
          .authorizeNode(node2.address, "Node", "laptop")
      ).to.be.revertedWith("AccessControl: caller is not owner");
    });
  });

  describe("Node Deauthorization", function () {
    it("should deauthorize a node", async function () {
      await accessControl.authorizeNode(node1.address, "Pi-Node-001", "pi");
      await accessControl.deauthorizeNode(node1.address);

      const nodeInfo = await accessControl.getNodeInfo(node1.address);
      expect(nodeInfo.active).to.equal(false);
    });

    it("should emit NodeDeauthorized event", async function () {
      await accessControl.authorizeNode(node1.address, "Pi-Node-001", "pi");

      await expect(accessControl.deauthorizeNode(node1.address))
        .to.emit(accessControl, "NodeDeauthorized")
        .withArgs(node1.address);
    });

    it("should prevent deauthorized node from calling protected functions", async function () {
      await accessControl.authorizeNode(node1.address, "Pi-Node-001", "pi");
      await accessControl.deauthorizeNode(node1.address);

      const hash = ethers.id("video");
      const ipHash = ethers.id("ip");
      await expect(
        accessControl
          .connect(node1)
          .registerVideo(hash, "phash", true, 8500, 0, 0, ipHash, "US", "NY", 0, 0, "{}")
      ).to.be.revertedWith("AccessControl: caller is not authorized");
    });
  });

  describe("Ownership", function () {
    it("should set deployer as owner", async function () {
      const contractOwner = await accessControl.owner();
      expect(contractOwner).to.equal(owner.address);
    });

    it("should transfer ownership", async function () {
      await accessControl.transferOwnership(node1.address);
      const newOwner = await accessControl.owner();
      expect(newOwner).to.equal(node1.address);
    });

    it("should reject non-owner ownership transfer", async function () {
      await expect(
        accessControl.connect(unauthorized).transferOwnership(node1.address)
      ).to.be.revertedWith("AccessControl: caller is not owner");
    });
  });

  describe("Node Count Tracking", function () {
    it("should track authorized node count", async function () {
      await accessControl.authorizeNode(node1.address, "Node-1", "pi");
      await accessControl.authorizeNode(node2.address, "Node-2", "laptop");

      const count = await accessControl.getAuthorizedNodeCount();
      expect(count).to.equal(2);
    });
  });
});
